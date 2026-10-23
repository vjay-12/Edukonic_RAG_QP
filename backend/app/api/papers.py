import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db, SessionLocal
from app.models import Paper, PaperQuestion, QuestionBank
from app.schemas import (
    PaperConfig,
    PaperDetailResponse,
    PaperListItem,
    QuestionUpdateRequest,
    QuestionRegenerateRequest,
    QuestionResponse,
    FinalizeResponse,
)
from app.services.generator import generate_paper_pipeline, generate_single_slot
from app.services.planner import compute_blueprint_report
from app.services.exporter import export_paper_docx, export_answer_key_docx

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/papers", tags=["Question Papers"])

def run_paper_generation_background(paper_id: int, config_data: Dict[str, Any]):
    """Background task to run full RAG generation pipeline without blocking the HTTP request."""
    with SessionLocal() as db:
        paper = db.query(Paper).filter(Paper.id == paper_id).first()
        if not paper:
            return

        try:
            paper.status = "generating"
            paper.progress = 5
            db.commit()

            cfg = PaperConfig(**config_data)

            def update_progress(pct: int, msg: str):
                paper.progress = pct
                db.commit()

            questions, report = generate_paper_pipeline(cfg, db, progress_callback=update_progress)

            # Store questions
            for q in questions:
                pq = PaperQuestion(
                    paper_id=paper.id,
                    slot_no=q["slot_no"],
                    section=q["section"],
                    type=q["type"],
                    marks=q["marks"],
                    chapter_no=q["chapter_no"],
                    topic=q["topic"],
                    difficulty=q["difficulty"],
                    competency=q["competency"],
                    bloom=q["bloom"],
                    content=q["content"],
                    source_chunk_ids=q["source_chunk_ids"],
                    validation=q["validation"],
                    status=q["status"],
                    embedding=q["embedding"]
                )
                db.add(pq)

            paper.status = "ready"
            paper.progress = 100
            paper.error = None
            db.commit()

        except Exception as e:
            logger.exception("Error generating paper %s", paper_id)
            paper.status = "failed"
            paper.error = str(e)
            db.commit()

@router.post("", response_model=Dict[str, Any])
def create_paper(
    payload: PaperConfig,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Create a new question paper and launch asynchronous generation in background."""
    config_dict = payload.model_dump(by_alias=True)

    db_paper = Paper(
        title=payload.title,
        config=config_dict,
        status="queued",
        progress=0,
        error=None
    )
    db.add(db_paper)
    db.commit()
    db.refresh(db_paper)

    # Launch generation in background
    background_tasks.add_task(run_paper_generation_background, db_paper.id, config_dict)

    return {
        "id": db_paper.id,
        "title": db_paper.title,
        "status": db_paper.status,
        "message": "Paper generation started in background."
    }

@router.get("", response_model=List[PaperListItem])
def list_papers(db: Session = Depends(get_db)):
    """List all generated papers for history table."""
    papers = db.query(Paper).order_by(Paper.created_at.desc()).all()
    results = []

    for p in papers:
        q_count = len(p.questions)
        total_marks = p.config.get("total_marks", sum(q.marks for q in p.questions))
        results.append(
            PaperListItem(
                id=p.id,
                title=p.title,
                total_marks=total_marks,
                question_count=q_count,
                status=p.status,
                progress=p.progress,
                created_at=p.created_at.isoformat(),
            )
        )
    return results

@router.get("/{paper_id}", response_model=PaperDetailResponse)
def get_paper_detail(paper_id: int, db: Session = Depends(get_db)):
    """Get complete paper details, questions, status, progress, and blueprint report."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    questions_out = []
    raw_qs = []
    for q in sorted(paper.questions, key=lambda x: x.slot_no):
        q_dict = {
            "slot_no": q.slot_no,
            "section": q.section,
            "type": q.type,
            "marks": q.marks,
            "chapter_no": q.chapter_no,
            "topic": q.topic,
            "difficulty": q.difficulty,
            "competency": q.competency,
            "bloom": q.bloom,
            "content": q.content,
            "source_chunk_ids": q.source_chunk_ids,
            "validation": q.validation,
            "status": q.status,
        }
        raw_qs.append(q_dict)
        questions_out.append(
            QuestionResponse(
                id=q.id,
                slot_no=q.slot_no,
                section=q.section,
                type=q.type,
                marks=q.marks,
                chapter_no=q.chapter_no,
                topic=q.topic,
                difficulty=q.difficulty,
                competency=q.competency,
                bloom=q.bloom,
                content=q.content,
                source_chunk_ids=q.source_chunk_ids,
                validation=q.validation,
                status=q.status,
            )
        )

    blueprint_rep = compute_blueprint_report([], raw_qs) if raw_qs else None

    return PaperDetailResponse(
        id=paper.id,
        title=paper.title,
        config=paper.config,
        status=paper.status,
        progress=paper.progress,
        error=paper.error,
        created_at=paper.created_at.isoformat(),
        questions=questions_out,
        blueprint_report=blueprint_rep,
    )

@router.patch("/{paper_id}/questions/{qid}")
def update_question(
    paper_id: int,
    qid: int,
    payload: QuestionUpdateRequest,
    db: Session = Depends(get_db)
):
    """Edit question content or update question status (accepted, rejected, draft)."""
    question = db.query(PaperQuestion).filter(
        PaperQuestion.paper_id == paper_id,
        PaperQuestion.id == qid
    ).first()

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    if payload.content is not None:
        question.content = payload.content
    if payload.status is not None:
        if payload.status not in ["accepted", "rejected", "draft"]:
            raise HTTPException(status_code=400, detail="Invalid status; must be accepted, rejected, or draft")
        question.status = payload.status

    db.commit()
    db.refresh(question)
    return {"status": "ok", "question_id": question.id, "new_status": question.status}

@router.post("/{paper_id}/questions/{qid}/regenerate")
def regenerate_question(
    paper_id: int,
    qid: int,
    payload: Optional[QuestionRegenerateRequest] = None,
    db: Session = Depends(get_db)
):
    """Regenerate a single question with optional teacher instruction."""
    question = db.query(PaperQuestion).filter(
        PaperQuestion.paper_id == paper_id,
        PaperQuestion.id == qid
    ).first()

    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    paper = db.query(Paper).filter(Paper.id == paper_id).first()

    # Collect existing paper embeddings excluding this question
    paper_embeddings = [
        list(q.embedding) for q in paper.questions 
        if q.id != qid and q.embedding is not None
    ]

    slot_spec = {
        "slot_no": question.slot_no,
        "section": question.section,
        "type": question.type,
        "marks": question.marks,
        "chapter_no": question.chapter_no,
        "difficulty": question.difficulty,
        "competency": question.competency,
        "bloom_hint": question.bloom,
    }

    instruction = payload.instruction if payload and payload.instruction else ""
    used_chunk_ids = set()

    try:
        new_content, new_val, stem_emb = generate_single_slot(
            slot=slot_spec,
            db=db,
            used_chunk_ids=used_chunk_ids,
            paper_embeddings=paper_embeddings,
            avoid_bank=True,
            custom_instruction=instruction
        )

        question.content = new_content
        question.validation = new_val
        question.embedding = stem_emb
        question.source_chunk_ids = new_content.get("source", {}).get("chunk_ids", [])
        question.topic = new_content.get("topic", question.topic)
        question.status = "draft"
        db.commit()
        db.refresh(question)

        return {
            "status": "ok",
            "question": {
                "id": question.id,
                "content": question.content,
                "validation": question.validation,
                "status": question.status
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Regeneration failed: {str(e)}")

@router.post("/{paper_id}/finalize")
def finalize_paper(paper_id: int, db: Session = Depends(get_db)):
    """Save all accepted questions from this paper into the Question Bank."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    accepted_questions = db.query(PaperQuestion).filter(
        PaperQuestion.paper_id == paper_id,
        PaperQuestion.status == "accepted"
    ).all()

    saved_count = 0
    for q in accepted_questions:
        # Check if already added
        bank_item = QuestionBank(
            content=q.content,
            class_num=paper.config.get("class", 10),
            subject=paper.config.get("subject", "Science"),
            chapter_no=q.chapter_no,
            type=q.type,
            marks=q.marks,
            difficulty=q.difficulty,
            competency=q.competency,
            source=q.content.get("source") if isinstance(q.content, dict) else {},
            embedding=q.embedding
        )
        db.add(bank_item)
        saved_count += 1

    db.commit()
    return {
        "status": "ok",
        "paper_id": paper_id,
        "saved_to_bank_count": saved_count,
        "message": f"Successfully saved {saved_count} accepted questions to the Question Bank!"
    }

@router.get("/{paper_id}/export")
def export_paper_download(
    paper_id: int,
    format: str = Query("docx", description="Export format: docx"),
    part: str = Query("paper", description="Export part: paper or key"),
    db: Session = Depends(get_db)
):
    """Download Question Paper or Answer Key in DOCX format."""
    paper = db.query(Paper).filter(Paper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")

    questions_data = [
        {
            "id": q.id,
            "slot_no": q.slot_no,
            "section": q.section,
            "type": q.type,
            "marks": q.marks,
            "chapter_no": q.chapter_no,
            "content": q.content,
        }
        for q in sorted(paper.questions, key=lambda x: x.slot_no)
    ]

    paper_dict = {
        "id": paper.id,
        "title": paper.title,
        "config": paper.config
    }

    if part == "key":
        stream = export_answer_key_docx(paper_dict, questions_data)
        filename = f"Answer_Key_Paper_{paper_id}.docx"
    else:
        stream = export_paper_docx(paper_dict, questions_data)
        filename = f"Question_Paper_{paper_id}.docx"

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
