import re
import math
from typing import List, Tuple, Optional, Dict, Any, Set
from sqlalchemy.orm import Session

from app.config import settings
from app.models import QuestionBank, ReferenceQuestion
from app.services.llm import embed_one

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two unit vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    return sum(a * b for a, b in zip(v1, v2))

def normalize_concept_key(concept: str, chapter_no: int) -> str:
    """
    Normalize concept string to a canonical key: ch{chapter_no}:{normalized_phrase}.
    e.g., 'Law of Conservation of Mass' -> 'ch1:law of conservation of mass'
    """
    if not concept:
        return f"ch{chapter_no}:general"
    clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', str(concept).lower()).strip()
    clean = re.sub(r'\s+', ' ', clean)
    # Strip leading 'chapter X' if included in the phrase
    clean = re.sub(r'^chapter\s+\d+\s*', '', clean).strip()
    return f"ch{chapter_no}:{clean}"

def check_duplicate(
    stem_embedding: List[float],
    comparison_embeddings: List[List[float]],
    threshold: Optional[float] = None
) -> Tuple[bool, float]:
    """Check if stem_embedding is similar to any comparison embedding above threshold."""
    thresh = threshold if threshold is not None else settings.DEDUPE_THRESHOLD
    max_sim = 0.0

    for emb in comparison_embeddings:
        sim = cosine_similarity(stem_embedding, emb)
        if sim > max_sim:
            max_sim = sim
        if max_sim >= thresh:
            return True, max_sim

    return False, max_sim

def is_question_duplicate(
    candidate_texts: List[str],
    paper_embeddings: List[List[float]],
    db: Session,
    chapter_no: Optional[int] = None,
    threshold: Optional[float] = None,
    avoid_bank: bool = True
) -> Tuple[bool, float, str, List[List[float]]]:
    """
    Check if ANY candidate text (main stem or sub-question stem separately) is a duplicate of:
    1. Earlier question or sub-question embeddings across the whole paper
    2. Approved questions in QuestionBank
    3. Reference questions
    Returns (is_dup, max_similarity, source_info, computed_embeddings).
    """
    thresh = threshold if threshold is not None else settings.DEDUPE_THRESHOLD
    computed_embeddings: List[List[float]] = []

    # 1. Embed each candidate text separately
    for text in candidate_texts:
        clean_text = text.strip()
        if not clean_text:
            continue
        emb = embed_one(clean_text, is_query=False)
        if not emb:
            continue
        computed_embeddings.append(emb)

        # Check against all previous paper embeddings
        for idx, prev_emb in enumerate(paper_embeddings):
            sim = cosine_similarity(emb, prev_emb)
            if sim >= thresh:
                return True, sim, f"earlier paper item (similarity: {sim:.3f})", computed_embeddings

    if not avoid_bank or not computed_embeddings:
        return False, 0.0, "", computed_embeddings

    # 2. Compare against QuestionBank in same chapter
    bank_query = db.query(QuestionBank)
    if chapter_no is not None:
        bank_query = bank_query.filter(QuestionBank.chapter_no == chapter_no)
    bank_items = bank_query.limit(200).all()

    for item in bank_items:
        if item.embedding is not None:
            emb_list = list(item.embedding)
            for c_emb in computed_embeddings:
                sim = cosine_similarity(c_emb, emb_list)
                if sim >= thresh:
                    return True, sim, f"question bank #{item.id} (similarity: {sim:.3f})", computed_embeddings

    # 3. Compare against ReferenceQuestion in same chapter
    ref_query = db.query(ReferenceQuestion)
    if chapter_no is not None:
        ref_query = ref_query.filter(ReferenceQuestion.chapter_no == chapter_no)
    ref_items = ref_query.limit(200).all()

    for ref in ref_items:
        if ref.embedding is not None:
            emb_list = list(ref.embedding)
            for c_emb in computed_embeddings:
                sim = cosine_similarity(c_emb, emb_list)
                if sim >= thresh:
                    return True, sim, f"reference exemplar #{ref.id} (similarity: {sim:.3f})", computed_embeddings

    return False, 0.0, "", computed_embeddings
