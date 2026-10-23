from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db import get_db
from app.models import Document, Chunk
from app.schemas import ChapterResponse

router = APIRouter(tags=["Chapters & Citations"])

@router.get("/chapters", response_model=List[ChapterResponse])
def get_ready_chapters(db: Session = Depends(get_db)):
    """List ready textbook chapters available for paper generation."""
    docs = db.query(Document).filter(Document.status == "ready").order_by(Document.chapter_no).all()
    results = []

    for d in docs:
        chunk_count = db.query(func.count(Chunk.id)).filter(Chunk.document_id == d.id).scalar() or 0
        results.append(
            ChapterResponse(
                chapter_no=d.chapter_no,
                chapter_title=d.chapter_title,
                page_count=d.page_count,
                chunks_count=chunk_count,
                status=d.status,
            )
        )
    return results

@router.get("/chunks/{chunk_id}")
def get_chunk_citation(chunk_id: int, db: Session = Depends(get_db)):
    """Retrieve full chunk text and metadata for teacher citation drawer."""
    chunk = db.query(Chunk).filter(Chunk.id == chunk_id).first()
    if not chunk:
        raise HTTPException(status_code=404, detail=f"Chunk #{chunk_id} not found.")

    doc = db.query(Document).filter(Document.id == chunk.document_id).first()
    doc_title = doc.chapter_title if doc else f"Chapter {chunk.chapter_no}"

    return {
        "id": chunk.id,
        "chapter_no": chunk.chapter_no,
        "chapter_title": doc_title,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "section_heading": chunk.section_heading,
        "content_type": chunk.content_type,
        "token_count": chunk.token_count,
        "text": chunk.text,
        "citation": f"NCERT Class 10 Science · Chapter {chunk.chapter_no} ({doc_title}) · Pages {chunk.page_start}-{chunk.page_end}"
    }
