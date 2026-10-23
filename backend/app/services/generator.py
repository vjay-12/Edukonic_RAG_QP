import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Callable
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import settings
from app.models import Chunk, Document, ReferenceQuestion
from app.schemas import PaperConfig, QuestionContent
from app.services.llm import generate_json, embed_one
from app.services.planner import plan_paper_slots, compute_blueprint_report
from app.services.dedupe import is_question_duplicate
from app.services.validator import validate_deterministic, validate_with_llm

logger = logging.getLogger(__name__)
PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

def load_prompt_file(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def select_anchor_and_context(
    chapter_no: int,
    slot_type: str,
    used_chunk_ids: set,
    db: Session,
    k_neighbors: int = 3
) -> Tuple[Optional[Chunk], List[Chunk], str]:
    """
    Select an anchor chunk from the chapter (preferring concept/example, avoiding reuse)
    and retrieve the top k_neighbors similar chunks in the same chapter.
    """
    # 1. Fetch eligible candidate chunks
    query = db.query(Chunk).filter(Chunk.chapter_no == chapter_no)
    all_chunks = query.all()
    if not all_chunks:
        return None, [], ""

    # Prefer unused chunks first
    unused = [c for c in all_chunks if c.id not in used_chunk_ids]
    pool = unused if unused else all_chunks

    # Prefer concept, example, activity
    type_priority = {
        "concept": 1,
        "example": 2,
        "activity": 3,
        "summary": 4,
        "exercise": 5
    }
    pool.sort(key=lambda c: type_priority.get(c.content_type, 6))
    anchor = pool[0]

    # 2. Retrieve top-k similar neighbor chunks in the same chapter
    neighbors: List[Chunk] = []
    if anchor.embedding is not None:
        emb_str = "[" + ",".join(str(x) for x in list(anchor.embedding)) + "]"
        raw_sql = text("""
            SELECT id FROM chunks 
            WHERE chapter_no = :ch AND id != :anchor_id
            ORDER BY embedding <=> (:emb)::vector
            LIMIT :k
        """)
        res = db.execute(raw_sql, {"ch": chapter_no, "anchor_id": anchor.id, "emb": emb_str, "k": k_neighbors}).fetchall()
        neighbor_ids = [row[0] for row in res]
        if neighbor_ids:
            neighbors = db.query(Chunk).filter(Chunk.id.in_(neighbor_ids)).all()

    # 3. Format full context text
    context_chunks = [anchor] + neighbors
    context_parts = []
    for c in context_chunks:
        head = c.section_heading or "Section"
        context_parts.append(f"--- [Chunk #{c.id} | Pages {c.page_start}-{c.page_end} | Type: {c.content_type} | Heading: {head}] ---\n{c.text.strip()}")

    full_context_text = "\n\n".join(context_parts)
    return anchor, context_chunks, full_context_text

def build_generation_prompt(
    slot: Dict[str, Any],
    anchor: Chunk,
    context_chunks: List[Chunk],
    context_text: str,
    extra_instruction: str = ""
) -> Tuple[str, str]:
    """Construct system instruction and user prompt for question generation."""
    sys_instruction = load_prompt_file("generate_system.md")

    type_file_map = {
        "mcq": "generate_mcq.md",
        "assertion_reason": "generate_assertion_reason.md",
        "vsa": "generate_vsa.md",
        "sa": "generate_sa.md",
        "la": "generate_la.md",
        "case": "generate_case.md",
    }
    type_prompt = load_prompt_file(type_file_map.get(slot["type"], "generate_mcq.md"))

    chunk_ids = [c.id for c in context_chunks]
    pages = sorted(list({p for c in context_chunks for p in range(c.page_start, c.page_end + 1)}))
    topic = anchor.section_heading or f"Chapter {slot['chapter_no']} Concept"

    user_prompt = f"""{type_prompt}

TASK: Generate a single CBSE Class 10 Science question conforming strictly to these slot specifications:
- Slot Number: {slot['slot_no']}
- Section: {slot['section']}
- Question Type: {slot['type']}
- Marks: {slot['marks']}
- Chapter Number: {slot['chapter_no']}
- Topic: {topic}
- Difficulty Level: {slot.get('difficulty', 'medium')}
- Competency-Based: {slot.get('competency', False)}
- Bloom's Taxonomy Hint: {slot.get('bloom_hint', 'understand')}
- Source Chunks Available: {chunk_ids}
- Source Pages: {pages}

--- BEGIN TEXTBOOK CONTEXT ---
{context_text}
--- END TEXTBOOK CONTEXT ---

{extra_instruction}

Ensure the question object contains:
- "slot_no": {slot['slot_no']}
- "type": "{slot['type']}"
- "marks": {slot['marks']}
- "stem": question statement
- "options": list of 4 choices if MCQ/Assertion-Reason, else null
- "correct_option": "A", "B", "C", or "D" if MCQ/Assertion-Reason, else null
- "sub_questions": list of sub-questions if case-based, else null
- "answer": complete model answer
- "marking_scheme": list of steps summing to {slot['marks']} marks
- "difficulty": "{slot.get('difficulty', 'medium')}"
- "competency": {json.dumps(slot.get('competency', False))}
- "bloom": "{slot.get('bloom_hint', 'understand')}"
- "chapter_no": {slot['chapter_no']}
- "topic": "{topic}"
- "source": {{"chunk_ids": {chunk_ids}, "pages": {pages}}}
- "insufficient_context": false
"""
    return sys_instruction, user_prompt

def generate_single_slot(
    slot: Dict[str, Any],
    db: Session,
    used_chunk_ids: set,
    paper_embeddings: List[List[float]],
    avoid_bank: bool = True,
    custom_instruction: str = ""
) -> Tuple[Dict[str, Any], Dict[str, Any], List[float]]:
    """
    Generate, validate, and deduplicate a single question slot with automatic one-time regeneration on defect.
    """
    ch_no = slot["chapter_no"]
    anchor, context_chunks, context_text = select_anchor_and_context(
        ch_no, slot["type"], used_chunk_ids, db, k_neighbors=settings.RETRIEVAL_NEIGHBORS
    )
    if not anchor:
        raise RuntimeError(f"No chunks found in database for chapter {ch_no}")

    used_chunk_ids.add(anchor.id)
    available_chunk_ids = [c.id for c in context_chunks]

    extra = custom_instruction
    attempts = 0
    max_attempts = 2

    final_q: Dict[str, Any] = {}
    final_val: Dict[str, Any] = {}
    stem_emb: List[float] = []

    while attempts < max_attempts:
        attempts += 1
        sys_inst, user_prompt = build_generation_prompt(slot, anchor, context_chunks, context_text, extra_instruction=extra)

        raw_q = generate_json(user_prompt, schema=QuestionContent, system_instruction=sys_inst)
        if not isinstance(raw_q, dict):
            raw_q = {}

        # Standardize source
        src = raw_q.get("source") or {}
        if not src.get("chunk_ids"):
            src["chunk_ids"] = available_chunk_ids
        if not src.get("pages"):
            src["pages"] = sorted(list({p for c in context_chunks for p in range(c.page_start, c.page_end + 1)}))
        raw_q["source"] = src
        raw_q["slot_no"] = slot["slot_no"]
        raw_q["chapter_no"] = slot["chapter_no"]
        raw_q["marks"] = slot["marks"]
        raw_q["type"] = slot["type"]

        # Deterministic checks
        is_det_ok, det_issues = validate_deterministic(raw_q, slot["marks"], slot["type"], available_chunk_ids)
        if not is_det_ok and attempts < max_attempts:
            extra = f"\nATTENTION: Previous attempt had deterministic errors:\n- " + "\n- ".join(det_issues) + "\nPlease correct these in the new question."
            continue

        # Dedupe check
        stem = raw_q.get("stem", "")
        stem_emb = embed_one(stem, is_query=False) if stem else []
        is_dup, max_sim, dup_src = is_question_duplicate(
            stem, paper_embeddings, db, chapter_no=ch_no, avoid_bank=avoid_bank
        )
        if is_dup and attempts < max_attempts:
            extra = f"\nATTENTION: Question was too similar to an existing question ({dup_src}). Formulate a completely different question from another part of the context."
            continue

        # LLM validation check
        val_res = validate_with_llm(raw_q, context_text)
        if val_res.get("verdict") == "fail" and attempts < max_attempts:
            issues = val_res.get("issues", [])
            extra = f"\nATTENTION: Previous attempt failed validation:\n- " + "\n- ".join(issues) + "\nPlease fix these issues."
            continue

        final_q = raw_q
        final_val = val_res
        break

    return final_q, final_val, stem_emb

def generate_paper_pipeline(
    config: PaperConfig,
    db: Session,
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Execute the complete paper generation pipeline:
    1. Plan slots according to config, weights, and mixes.
    2. Sequentially generate each slot with targeted context, deterministic checks, LLM validation, and dedupe.
    3. Generate the blueprint summary report.
    """
    if progress_callback:
        progress_callback(5, "Planning paper blueprint and slot allocation...")

    slots = plan_paper_slots(config)
    total_slots = len(slots)
    if total_slots == 0:
        raise ValueError("Paper configuration contains 0 question slots.")

    used_anchor_ids = set()
    paper_embeddings: List[List[float]] = []
    generated_questions: List[Dict[str, Any]] = []

    for idx, slot in enumerate(slots, 1):
        pct = 10 + int((idx / total_slots) * 80)
        if progress_callback:
            progress_callback(pct, f"Generating question {idx}/{total_slots} ({slot['type'].upper()}, Ch {slot['chapter_no']})...")

        q_content, val_result, stem_emb = generate_single_slot(
            slot=slot,
            db=db,
            used_chunk_ids=used_anchor_ids,
            paper_embeddings=paper_embeddings,
            avoid_bank=config.avoid_duplicates_from_bank
        )

        if stem_emb:
            paper_embeddings.append(stem_emb)

        # Assemble question record
        q_record = {
            "slot_no": slot["slot_no"],
            "section": slot["section"],
            "type": slot["type"],
            "marks": slot["marks"],
            "chapter_no": slot["chapter_no"],
            "topic": q_content.get("topic", f"Chapter {slot['chapter_no']}"),
            "difficulty": slot.get("difficulty", "medium"),
            "competency": slot.get("competency", False),
            "bloom": slot.get("bloom_hint", "understand"),
            "content": q_content,
            "source_chunk_ids": q_content.get("source", {}).get("chunk_ids", []),
            "validation": val_result,
            "status": "draft" if val_result.get("verdict") != "fail" else "draft",
            "embedding": stem_emb
        }
        generated_questions.append(q_record)

    if progress_callback:
        progress_callback(95, "Computing blueprint report and finalizing paper...")

    report = compute_blueprint_report(slots, generated_questions)

    if progress_callback:
        progress_callback(100, "Generation complete.")

    return generated_questions, report
