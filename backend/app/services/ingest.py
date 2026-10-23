import os
from pathlib import Path
from typing import Optional, List, Dict, Any
import yaml
import pymupdf4llm
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Document, Chunk
from app.services.chunker import chunk_markdown_pages
from app.services.llm import embed

def ingest_chapter(
    manifest_data: Dict[str, Any],
    chapter_info: Dict[str, Any],
    books_base_dir: Path,
    db: Session,
    force: bool = False,
) -> Dict[str, Any]:
    """Ingest a single chapter PDF: parse, chunk, embed, and save to DB."""
    class_num = manifest_data.get("class", 10)
    subject = manifest_data.get("subject", "Science")
    edition_year = manifest_data.get("edition_year", 2026)

    chapter_no = chapter_info["chapter_no"]
    chapter_title = chapter_info["title"]
    pdf_rel_path = chapter_info["file"]
    pdf_full_path = (books_base_dir / pdf_rel_path).resolve()

    if not pdf_full_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_full_path}")

    # Check for existing document
    existing = db.query(Document).filter(
        Document.class_num == class_num,
        Document.subject == subject,
        Document.chapter_no == chapter_no,
        Document.edition_year == edition_year,
    ).first()

    if existing:
        if not force:
            return {
                "chapter_no": chapter_no,
                "title": chapter_title,
                "status": "skipped",
                "message": "Already ingested. Use --force to re-ingest.",
                "chunks_count": len(existing.chunks),
            }
        else:
            db.delete(existing)
            db.commit()

    # 1. Parse PDF pages to markdown
    pages_data = pymupdf4llm.to_markdown(str(pdf_full_path), page_chunks=True)
    page_count = len(pages_data)

    # 2. Chunk markdown
    chunks_meta = chunk_markdown_pages(pages_data, chapter_no=chapter_no)
    if not chunks_meta:
        raise ValueError(f"No chunks generated for chapter {chapter_no} from {pdf_full_path}")

    # 3. Create document record
    doc = Document(
        class_num=class_num,
        subject=subject,
        chapter_no=chapter_no,
        chapter_title=chapter_title,
        edition_year=edition_year,
        source_file=str(pdf_rel_path),
        page_count=page_count,
        status="processing",
    )
    db.add(doc)
    db.flush()

    # 4. Embed chunks in batches
    chunk_texts = [c["text"] for c in chunks_meta]
    embeddings = embed(chunk_texts, is_query=False)

    # 5. Insert chunks
    chunk_objs = []
    for meta, emb in zip(chunks_meta, embeddings):
        chunk = Chunk(
            document_id=doc.id,
            chapter_no=chapter_no,
            page_start=meta["page_start"],
            page_end=meta["page_end"],
            section_heading=meta["section_heading"],
            content_type=meta["content_type"],
            text=meta["text"],
            token_count=meta["token_count"],
            embedding=emb,
        )
        chunk_objs.append(chunk)

    db.add_all(chunk_objs)
    doc.status = "ready"
    db.commit()

    return {
        "chapter_no": chapter_no,
        "title": chapter_title,
        "status": "ready",
        "page_count": page_count,
        "chunks_count": len(chunk_objs),
    }

def ingest_manifest(
    manifest_path: str,
    chapter_filter: Optional[int] = None,
    force: bool = False,
) -> List[Dict[str, Any]]:
    """Parse manifest and ingest all chapters or a specified chapter."""
    m_path = Path(manifest_path).resolve()
    if not m_path.exists():
        raise FileNotFoundError(f"Manifest not found: {m_path}")

    with open(m_path, "r", encoding="utf-8") as f:
        manifest_data = yaml.safe_load(f)

    books_base_dir = m_path.parent
    results = []

    with SessionLocal() as db:
        for ch in manifest_data.get("chapters", []):
            if chapter_filter is not None and ch["chapter_no"] != chapter_filter:
                continue
            res = ingest_chapter(manifest_data, ch, books_base_dir, db, force=force)
            results.append(res)

    return results
