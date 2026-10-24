import json
import logging
from typing import List, Dict, Any, Tuple, Optional, Callable, Set
from pathlib import Path
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import Document, Chunk
from app.schemas import PaperConfig, QuestionContent
from app.config import settings
from app.services.llm import (
    generate_json,
    embed_one,
    reset_llm_stats,
    get_llm_stats,
    get_llm_usage_summary,
)
from app.services.planner import plan_paper_slots, compute_blueprint_report
from app.services.validator import validate_deterministic, validate_with_llm
from app.services.dedupe import is_question_duplicate, normalize_concept_key
from app.services.text_utils import (
    sanitize_question_content,
    build_canonical_citation,
    extract_reaction_signatures
)

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

def load_prompt_file(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

CHAPTER_11_SUBTOPIC_SCHEDULE = {
    1: "11.1 Electric",           # Slot 1: MCQ (11.1 Electric Current & Circuit)
    2: "11.2 ELECTRIC POTENTIAL", # Slot 2: MCQ (11.2 Electric Potential Difference)
    3: "11.4 Ohm's Law (V-I",     # Slot 3: MCQ (11.4 Ohm's Law V-I Relationship)
    4: "11.5 Factors",            # Slot 4: MCQ (11.5 Factors on Resistance / Resistivity)
    5: "11.6.1 Resistors",        # Slot 5: MCQ (11.6.1 Resistors in Series)
    6: "11.6.2 Resistors",        # Slot 6: MCQ (11.6.2 Resistors in Parallel)
    7: "11.1 Electric",           # Slot 7: VSA (11.1 Electric Current Definition, I = Q/t)
    8: "11.5 Factors on which Resistance of a Conductor Depends (Table 11.2", # Slot 8: VSA (Alloys vs pure metals in heating elements)
    9: "11.7.1 Joule",           # Slot 9: SA (11.7.1 Joule's Law of Heating)
    10: "11.8 ELECTRIC",          # Slot 10: SA (11.8 Electric Power)
    11: "11.3 CIRCUIT",           # Slot 11: LA (11.3 Circuit diagram components & Ohm's law)
    12: "11.7.1 Practical",       # Slot 12: Case (11.7.1 Practical Applications: Domestic appliance ratings, current drawn, and fuse wire safety with concrete data)
}

def select_anchor_and_context(
    chapter_no: int,
    slot_type: str,
    used_chunk_ids: set,
    db: Session,
    k_neighbors: int = 3,
    slot_no: Optional[int] = None,
    target_subtopic: Optional[str] = None
) -> Tuple[Optional[Chunk], List[Chunk], str]:
    """
    Select an unused anchor chunk from the specified chapter and retrieve its surrounding context.
    Filters out non-concept chunks (e.g. 'What you have learnt', 'Questions', 'Exercises')
    and spreads questions across distinct subtopics of the chapter.
    """
    query = (
        db.query(Chunk)
        .join(Document, Chunk.document_id == Document.id)
        .filter(Chunk.chapter_no == chapter_no)
    )

    # Core concept sourcing: NEVER pick primary anchor from 'What you have learnt', 'Questions', or 'Exercises'
    for excl in ["what you have learnt", "questions", "exercises"]:
        query = query.filter(~Chunk.section_heading.ilike(f"%{excl}%"))

    # Determine targeted subtopic if specified or scheduled
    scheduled_subtopic = target_subtopic
    if not scheduled_subtopic and chapter_no == 11 and slot_no and slot_no in CHAPTER_11_SUBTOPIC_SCHEDULE:
        scheduled_subtopic = CHAPTER_11_SUBTOPIC_SCHEDULE[slot_no]

    anchor: Optional[Chunk] = None

    if scheduled_subtopic:
        sub_query = query.filter(Chunk.section_heading.ilike(f"%{scheduled_subtopic}%"))
        if used_chunk_ids:
            unused_sub = sub_query.filter(~Chunk.id.in_(used_chunk_ids))
            anchor = unused_sub.order_by(Chunk.token_count.desc()).first()
        if not anchor:
            anchor = sub_query.order_by(Chunk.token_count.desc()).first()

    if not anchor:
        if used_chunk_ids:
            unused_query = query.filter(~Chunk.id.in_(used_chunk_ids))
            if slot_type in ["case", "la"]:
                anchor = unused_query.order_by(Chunk.token_count.desc()).first()
            else:
                anchor = unused_query.order_by(func.random()).first()

    if not anchor:
        if slot_type in ["case", "la"]:
            anchor = query.order_by(Chunk.token_count.desc()).first()
        else:
            anchor = query.order_by(func.random()).first()

    if not anchor:
        return None, [], ""

    window_chunks = (
        db.query(Chunk)
        .filter(
            Chunk.document_id == anchor.document_id,
            Chunk.id >= max(1, anchor.id - 1),
            Chunk.id <= anchor.id + 1
        )
        .order_by(Chunk.id)
        .all()
    )

    context_chunks = window_chunks if window_chunks else [anchor]

    context_parts = []
    for c in context_chunks:
        header = f"[Chunk #{c.id} | Ch {c.chapter_no}: {c.section_heading or 'Text'} | pp. {c.page_start}-{c.page_end}]"
        context_parts.append(f"{header}\n{c.text}")

    full_context_text = "\n\n".join(context_parts)
    return anchor, context_chunks, full_context_text

def build_generation_prompt(
    slot: Dict[str, Any],
    anchor: Chunk,
    context_chunks: List[Chunk],
    context_text: str,
    extra_instruction: str = "",
    used_reactions: Optional[Set[str]] = None
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

    numerical_directive = ""
    if slot.get("is_numerical"):
        numerical_directive = """
MANDATORY NUMERICAL REQUIREMENT:
This question MUST be a calculation-based problem for Chapter 11 (Electricity).
Formulate a problem using numerical values from the context or standard curriculum (e.g. Ohm's Law V = I·R, Equivalent resistance in series/parallel, Electric power P = V·I = I²R = V²/R, Joule's heating H = I²Rt, or Electric current I = Q/t).
The student MUST be asked to calculate a numerical answer.

MANDATORY NUMERICAL MARKING SCHEME:
The `marking_scheme` array MUST explicitly test one point each (1 mark each):
1. Formula step: Formula stated with correct symbols [1 mark]
2. Substitution step: Substitution of given values [1 mark]
3. Final Answer step: Final calculated numerical result with correct SI unit [1 mark]
(NOTE: If the question asks for a ratio or an expression in terms of a variable like R, do NOT demand units).
"""

    case_directive = ""
    if slot["type"] == "case":
        case_directive = """
MANDATORY CASE-BASED REQUIREMENT:
1. REAL-LIFE SCENARIO WITH CONCRETE DATA (Requirement 3): The stem MUST start with an authentic applied / real-life or experimental scenario (80–130 words) CONTAINING CONCRETE NUMERICAL DATA READINGS (e.g. domestic appliances with voltage/wattage ratings like 'A 220 V domestic circuit supplies an electric heater rated 1000 W and an electric iron rated 750 W...' or measured circuit readings).
   Focus on ONE single coherent situation requiring students to apply scientific reasoning and calculate.
   End the passage with: "Based on the above information, answer the following questions:"
2. Provide exactly 3 sub-questions in `sub_questions` summing to 4 marks:
   - Sub-question (i): 1 mark
   - Sub-question (ii): 1 mark
   - Sub-question (iii): 2 marks (split into 1 + 1 marks for two distinct scientific points)
3. Answers to the sub-questions MUST NOT appear verbatim in the passage!
4. The `answer` field of the question object MUST provide complete, comprehensive model answers for all sub-questions ((i), (ii), (iii)), NOT meta placeholders like "Sub-questions evaluate...".
5. The marking scheme MUST test one point each (split 2-mark step into 1 + 1).
"""

    reaction_exclusions = ""
    if used_reactions:
        reaction_exclusions = f"""
EXCLUDED EXPERIMENTS & REACTIONS:
The following chemical reactions, experiments, or setups have ALREADY been tested elsewhere in this paper.
You MUST NOT repeat or test any of these in this question:
{', '.join(sorted(used_reactions))}
"""

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
- Is Numerical: {slot.get('is_numerical', False)}
- Source Chunks Available: {chunk_ids}
- Source Pages: {pages}

{numerical_directive}
{case_directive}
{reaction_exclusions}

--- BEGIN TEXTBOOK CONTEXT ---
{context_text}
--- END TEXTBOOK CONTEXT ---

{extra_instruction}

Ensure the question object contains:
- "slot_no": {slot['slot_no']}
- "type": "{slot['type']}"
- "marks": {slot['marks']}
- "stem": question statement (complete and unambiguous; NEVER refer to diagrams, figures, or phantom 'provided text' unless fully printed in text. NEVER state the answer in an MCQ stem!)
- "concept_key": specific scientific law or core concept tested in lowercase (e.g. "law of conservation of mass", "ohm's law", "thermal decomposition")
- "is_numerical": {json.dumps(bool(slot.get('is_numerical', False)))}
- "options": list of 4 choices if MCQ/Assertion-Reason, else null (WITHOUT any "A)", "B)" prefix)
- "correct_option": "A", "B", "C", or "D" if MCQ/Assertion-Reason, else null
- "sub_questions": list of sub-questions if case-based or long-answer, else null
- "answer": complete model answer (NO hallucinated specific numeric figures like melting points unless directly in the source chunk)
- "marking_scheme": list of steps testing one point each (summing to {slot['marks']} marks, with 1 mark per step)
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
    paper_concept_keys: Set[str],
    paper_concept_tags: Set[str],
    paper_reactions: Set[str],
    avoid_bank: bool = True,
    custom_instruction: str = "",
    exemplar_texts: Optional[List[str]] = None
) -> Tuple[Dict[str, Any], Dict[str, Any], List[List[float]], str, List[str], List[str]]:
    """
    Generate, validate, and deduplicate a single question slot with automatic one-time regeneration on defect.
    Embeds each sub-question separately, rejects duplicate concept keys, enforces copy guard, and enforces concept deduplication.
    """
    ch_no = slot["chapter_no"]
    slot_no = slot["slot_no"]
    anchor, context_chunks, context_text = select_anchor_and_context(
        ch_no, slot["type"], used_chunk_ids, db, k_neighbors=settings.RETRIEVAL_NEIGHBORS, slot_no=slot_no
    )
    if not anchor:
        raise RuntimeError(f"No chunks found in database for chapter {ch_no}")

    used_chunk_ids.add(anchor.id)
    available_chunk_ids = [c.id for c in context_chunks]

    # Retrieve Document for chapter title
    doc = db.query(Document).filter(Document.id == anchor.document_id).first()
    ch_title = doc.chapter_title if doc else f"Chapter {ch_no}"

    # Build canonical citation: "NCERT Class 10 Science, Ch <no> <title>, <section heading>, p.<page> (chunk <id>)"
    citation_str = build_canonical_citation(
        chapter_no=ch_no,
        chapter_title=ch_title,
        section_heading=anchor.section_heading,
        page_start=anchor.page_start,
        page_end=anchor.page_end,
        chunk_id=anchor.id
    )

    extra = custom_instruction
    attempts = 0
    max_attempts = 4

    final_q: Dict[str, Any] = {}
    final_val: Dict[str, Any] = {}
    candidate_embeddings: List[List[float]] = []
    canonical_concept_key: str = ""
    discovered_reactions: List[str] = []
    discovered_concept_tags: List[str] = []

    all_exemplars = (exemplar_texts or []) + [c.text for c in context_chunks if c.text]

    while attempts < max_attempts:
        attempts += 1
        sys_inst, user_prompt = build_generation_prompt(
            slot, anchor, context_chunks, context_text,
            extra_instruction=extra,
            used_reactions=paper_reactions
        )

        raw_q = generate_json(user_prompt, schema=QuestionContent, system_instruction=sys_inst, model=settings.GEN_MODEL)
        if not isinstance(raw_q, dict):
            raw_q = {}

        # Standardize source & metadata with rich canonical citation
        pages = sorted(list({p for c in context_chunks for p in range(c.page_start, c.page_end + 1)}))
        raw_q["source"] = {
            "source_type": "ncert",
            "book": "NCERT Class 10 Science",
            "chapter_no": ch_no,
            "chapter_title": ch_title,
            "section_heading": anchor.section_heading or "Textbook Section",
            "page_start": anchor.page_start,
            "page_end": anchor.page_end,
            "pages": pages,
            "primary_chunk_id": anchor.id,
            "chunk_ids": available_chunk_ids,
            "citation": citation_str
        }
        raw_q["slot_no"] = slot["slot_no"]
        raw_q["chapter_no"] = slot["chapter_no"]
        raw_q["marks"] = slot["marks"]
        raw_q["type"] = slot["type"]
        raw_q["is_numerical"] = slot.get("is_numerical", False)

        # Sanitize texts (format chemical/physics expressions, strip option prefixes, strictly 1-mark steps, remove duplicate (a)(b) lead-ins)
        raw_q = sanitize_question_content(raw_q)

        # 1. Concept Key & Concept Tags detection (Requirement 1 & 2)
        raw_concept = raw_q.get("concept_key") or raw_q.get("topic") or "general"
        canonical_concept_key = normalize_concept_key(raw_concept, ch_no)
        raw_q["concept_key"] = canonical_concept_key

        from app.services.text_utils import detect_question_concepts
        discovered_concept_tags = detect_question_concepts(raw_q.get("stem", "") + " " + str(raw_q.get("answer", "")))

        # 2. Deterministic checks (includes 8-gram copy guard, concept dedupe, CBSE current definition, integer step marks, etc.)
        is_det_ok, det_issues = validate_deterministic(
            raw_q,
            slot["marks"],
            slot["type"],
            available_chunk_ids,
            is_numerical=slot.get("is_numerical", False),
            context_text=context_text,
            used_reactions=paper_reactions,
            exemplar_texts=all_exemplars,
            used_concepts=paper_concept_tags
        )
        if not is_det_ok and attempts < max_attempts:
            extra = f"\nATTENTION: Previous attempt had deterministic errors:\n- " + "\n- ".join(det_issues) + "\nPlease correct these in the new question."
            continue

        if canonical_concept_key in paper_concept_keys and attempts < max_attempts:
            extra = (
                f"\nATTENTION: Concept key '{canonical_concept_key}' was already tested in this paper. "
                f"You MUST formulate a question testing a completely different scientific concept from Chapter {ch_no}."
            )
            continue

        # 3. Dedupe check (Requirement 1: embed main stem and each sub-question separately)
        candidate_texts = [raw_q.get("stem", "")]
        for sq in raw_q.get("sub_questions") or []:
            if isinstance(sq, dict) and sq.get("stem"):
                candidate_texts.append(sq["stem"])

        is_dup, max_sim, dup_src, candidate_embeddings = is_question_duplicate(
            candidate_texts=candidate_texts,
            paper_embeddings=paper_embeddings,
            db=db,
            chapter_no=ch_no,
            avoid_bank=avoid_bank
        )
        if is_dup and attempts < max_attempts:
            extra = (
                f"\nATTENTION: A question stem or sub-question was too similar to an existing question ({dup_src}). "
                f"Formulate a completely different question on another topic in this chapter."
            )
            continue

        # 4. LLM validation check
        val_res = validate_with_llm(raw_q, context_text)
        if val_res.get("verdict") == "fail" and attempts < max_attempts:
            issues = val_res.get("issues", [])
            extra = f"\nATTENTION: Previous attempt failed validation:\n- " + "\n- ".join(issues) + "\nPlease fix these issues."
            continue

        discovered_reactions = extract_reaction_signatures(raw_q.get("stem", "") + " " + str(raw_q.get("answer", "")))
        final_q = raw_q
        final_val = val_res
        break

    return final_q, final_val, candidate_embeddings, canonical_concept_key, discovered_reactions, discovered_concept_tags

def generate_paper_pipeline(
    config: PaperConfig,
    db: Session,
    progress_callback: Optional[Callable[[int, str], None]] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Execute the complete paper generation pipeline:
    1. Plan slots according to config, weights, mark constraints, and numerical requirements.
    2. Sequentially generate each slot with targeted context, deterministic checks, LLM validation, dedupe, and reaction tracking.
    3. Generate the blueprint summary report.
    """
    if progress_callback:
        progress_callback(5, "Planning paper blueprint and slot allocation...")

    reset_llm_stats()

    slots = plan_paper_slots(config)
    total_slots = len(slots)
    if total_slots == 0:
        raise ValueError("Paper configuration contains 0 question slots.")

    used_anchor_ids = set()
    paper_embeddings: List[List[float]] = []
    paper_concept_keys: Set[str] = set()
    paper_concept_tags: Set[str] = set()
    paper_reactions: Set[str] = set()
    generated_questions: List[Dict[str, Any]] = []

    # Pre-fetch all exemplar/exercise texts for copy guard (8-gram check)
    chapter_nos = [c.chapter_no if hasattr(c, "chapter_no") else (c["chapter_no"] if isinstance(c, dict) else c) for c in config.chapters]
    exemplar_chunks = (
        db.query(Chunk)
        .filter(
            Chunk.chapter_no.in_(chapter_nos),
            (
                Chunk.section_heading.ilike("%example%") |
                Chunk.section_heading.ilike("%exercise%") |
                Chunk.section_heading.ilike("%question%") |
                Chunk.section_heading.ilike("%what you have learnt%")
            )
        )
        .all()
    )
    all_exemplar_texts = [c.text for c in exemplar_chunks if c.text]

    for idx, slot in enumerate(slots, 1):
        pct = 10 + int((idx / total_slots) * 80)
        num_str = " (NUMERICAL)" if slot.get("is_numerical") else ""
        if progress_callback:
            progress_callback(pct, f"Generating question {idx}/{total_slots} ({slot['type'].upper()}{num_str}, Ch {slot['chapter_no']})...")

        q_content, val_result, cand_embs, concept_key, rxns, tags = generate_single_slot(
            slot=slot,
            db=db,
            used_chunk_ids=used_anchor_ids,
            paper_embeddings=paper_embeddings,
            paper_concept_keys=paper_concept_keys,
            paper_concept_tags=paper_concept_tags,
            paper_reactions=paper_reactions,
            avoid_bank=config.avoid_duplicates_from_bank,
            exemplar_texts=all_exemplar_texts
        )

        # Store all embeddings and concept tags for cross-paper deduplication
        if cand_embs:
            paper_embeddings.extend(cand_embs)
        if concept_key:
            paper_concept_keys.add(concept_key)
        if rxns:
            paper_reactions.update(rxns)
        if tags:
            paper_concept_tags.update(tags)

        primary_emb = cand_embs[0] if cand_embs else None
        q_content["concept_tags"] = tags

        # Assemble question record
        q_record = {
            "slot_no": slot["slot_no"],
            "section": slot["section"],
            "type": slot["type"],
            "marks": slot["marks"],
            "chapter_no": slot["chapter_no"],
            "topic": q_content.get("topic", f"Chapter {slot['chapter_no']}"),
            "concept_key": concept_key,
            "concept_tags": tags,
            "is_numerical": slot.get("is_numerical", False),
            "difficulty": slot.get("difficulty", "medium"),
            "competency": slot.get("competency", False),
            "bloom": slot.get("bloom_hint", "understand"),
            "content": q_content,
            "source_chunk_ids": q_content.get("source", {}).get("chunk_ids", []),
            "validation": val_result,
            "status": "draft",
            "embedding": primary_emb
        }
        generated_questions.append(q_record)

    if progress_callback:
        progress_callback(95, "Computing blueprint report and finalizing paper...")

    report = compute_blueprint_report(slots, generated_questions)
    llm_usage = get_llm_stats()
    report["llm_usage"] = llm_usage
    report["llm_usage_summary"] = get_llm_usage_summary()

    if progress_callback:
        progress_callback(100, f"Generation complete. {get_llm_usage_summary()}")

    return generated_questions, report
