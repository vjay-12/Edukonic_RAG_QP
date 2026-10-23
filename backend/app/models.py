from datetime import datetime, timezone
from typing import Optional, List, Any
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    Boolean,
    ARRAY,
)
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

from app.db import Base
from app.config import settings

def utc_now():
    return datetime.now(timezone.utc)

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    class_num = Column("class", Integer, nullable=False, default=10)
    subject = Column(String(100), nullable=False, default="Science")
    chapter_no = Column(Integer, nullable=False)
    chapter_title = Column(String(255), nullable=False)
    edition_year = Column(Integer, nullable=False, default=2026)
    source_file = Column(String(500), nullable=False)
    page_count = Column(Integer, nullable=False, default=0)
    status = Column(String(50), nullable=False, default="processing")  # processing, ready, failed
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    chunks = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")

class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    chapter_no = Column(Integer, nullable=False, index=True)
    page_start = Column(Integer, nullable=False)
    page_end = Column(Integer, nullable=False)
    section_heading = Column(String(255), nullable=True)
    content_type = Column(String(50), nullable=False)  # concept, example, exercise, activity, summary
    text = Column(Text, nullable=False)
    token_count = Column(Integer, nullable=False, default=0)
    embedding = Column(Vector(settings.EMBED_DIM), nullable=True)

    document = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index("idx_chunks_chapter_no", "chapter_no"),
        Index("idx_chunks_content_type", "content_type"),
    )

class Paper(Base):
    __tablename__ = "papers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    config = Column(JSON, nullable=False)
    status = Column(String(50), nullable=False, default="queued")  # queued, planning, generating, validating, ready, failed
    progress = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    questions = relationship("PaperQuestion", back_populates="paper", cascade="all, delete-orphan")

class PaperQuestion(Base):
    __tablename__ = "paper_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paper_id = Column(Integer, ForeignKey("papers.id", ondelete="CASCADE"), nullable=False)
    slot_no = Column(Integer, nullable=False)
    section = Column(String(10), nullable=False)
    type = Column(String(50), nullable=False)  # mcq, assertion_reason, vsa, sa, la, case
    marks = Column(Integer, nullable=False)
    chapter_no = Column(Integer, nullable=False)
    topic = Column(String(255), nullable=True)
    difficulty = Column(String(50), nullable=True)  # easy, medium, hard
    competency = Column(Boolean, default=False, nullable=False)
    bloom = Column(String(50), nullable=True)
    content = Column(JSON, nullable=True)
    source_chunk_ids = Column(ARRAY(Integer), nullable=True)
    validation = Column(JSON, nullable=True)
    status = Column(String(50), nullable=False, default="draft")  # draft, accepted, rejected
    embedding = Column(Vector(settings.EMBED_DIM), nullable=True)

    paper = relationship("Paper", back_populates="questions")

class QuestionBank(Base):
    __tablename__ = "question_bank"

    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(JSON, nullable=False)
    class_num = Column("class", Integer, nullable=False, default=10)
    subject = Column(String(100), nullable=False, default="Science")
    chapter_no = Column(Integer, nullable=False)
    type = Column(String(50), nullable=False)
    marks = Column(Integer, nullable=False)
    difficulty = Column(String(50), nullable=True)
    competency = Column(Boolean, default=False, nullable=False)
    source = Column(JSON, nullable=True)
    embedding = Column(Vector(settings.EMBED_DIM), nullable=True)
    approved_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

class ReferenceQuestion(Base):
    __tablename__ = "reference_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(100), nullable=False)  # e.g. "CBSE Sample Paper 2024"
    year = Column(Integer, nullable=True)
    marks = Column(Integer, nullable=False)
    type = Column(String(50), nullable=False)
    chapter_no = Column(Integer, nullable=True)
    text = Column(Text, nullable=False)
    competency = Column(Boolean, default=False, nullable=False)
    embedding = Column(Vector(settings.EMBED_DIM), nullable=True)
