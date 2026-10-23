from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import QuestionBank
from app.schemas import BankItemResponse

router = APIRouter(prefix="/bank", tags=["Question Bank"])

@router.get("", response_model=List[BankItemResponse])
def get_question_bank(
    chapter: Optional[int] = Query(None, description="Filter by chapter number"),
    type: Optional[str] = Query(None, description="Filter by question type (mcq, sa, etc.)"),
    marks: Optional[int] = Query(None, description="Filter by marks"),
    difficulty: Optional[str] = Query(None, description="Filter by difficulty"),
    limit: int = Query(50, description="Max items to return"),
    db: Session = Depends(get_db)
):
    """Retrieve approved questions from the Question Bank with optional filters."""
    query = db.query(QuestionBank)

    if chapter is not None:
        query = query.filter(QuestionBank.chapter_no == chapter)
    if type is not None:
        query = query.filter(QuestionBank.type == type)
    if marks is not None:
        query = query.filter(QuestionBank.marks == marks)
    if difficulty is not None:
        query = query.filter(QuestionBank.difficulty == difficulty)

    items = query.order_by(QuestionBank.approved_at.desc()).limit(limit).all()

    results = []
    for it in items:
        results.append(
            BankItemResponse(
                id=it.id,
                class_num=it.class_num,
                subject=it.subject,
                chapter_no=it.chapter_no,
                type=it.type,
                marks=it.marks,
                difficulty=it.difficulty,
                competency=it.competency,
                content=it.content,
                approved_at=it.approved_at.isoformat(),
            )
        )
    return results
