import math
from typing import List, Tuple, Optional
from sqlalchemy.orm import Session

from app.config import settings
from app.models import QuestionBank, ReferenceQuestion
from app.services.llm import embed_one

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two unit vectors."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    return sum(a * b for a, b in zip(v1, v2))

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
    stem: str,
    paper_embeddings: List[List[float]],
    db: Session,
    chapter_no: Optional[int] = None,
    threshold: Optional[float] = None,
    avoid_bank: bool = True
) -> Tuple[bool, float, str]:
    """
    Check if a question stem is a duplicate of:
    1. Earlier questions in the current paper
    2. Approved questions in QuestionBank
    3. Reference questions
    Returns (is_dup, max_similarity, source_info).
    """
    stem_emb = embed_one(stem, is_query=False)
    thresh = threshold if threshold is not None else settings.DEDUPE_THRESHOLD

    # 1. Compare with current paper questions
    for idx, prev_emb in enumerate(paper_embeddings):
        sim = cosine_similarity(stem_emb, prev_emb)
        if sim >= thresh:
            return True, sim, f"current paper (question #{idx + 1}, similarity: {sim:.3f})"

    if not avoid_bank:
        return False, 0.0, ""

    # 2. Compare with QuestionBank in same chapter
    bank_query = db.query(QuestionBank)
    if chapter_no is not None:
        bank_query = bank_query.filter(QuestionBank.chapter_no == chapter_no)
    bank_items = bank_query.limit(200).all()

    for item in bank_items:
        if item.embedding is not None:
            # item.embedding may be an array/list or pgvector Vector
            emb_list = list(item.embedding)
            sim = cosine_similarity(stem_emb, emb_list)
            if sim >= thresh:
                return True, sim, f"question bank #{item.id} (similarity: {sim:.3f})"

    # 3. Compare with ReferenceQuestion in same chapter
    ref_query = db.query(ReferenceQuestion)
    if chapter_no is not None:
        ref_query = ref_query.filter(ReferenceQuestion.chapter_no == chapter_no)
    ref_items = ref_query.limit(200).all()

    for ref in ref_items:
        if ref.embedding is not None:
            emb_list = list(ref.embedding)
            sim = cosine_similarity(stem_emb, emb_list)
            if sim >= thresh:
                return True, sim, f"reference exemplar #{ref.id} (similarity: {sim:.3f})"

    return False, 0.0, ""
