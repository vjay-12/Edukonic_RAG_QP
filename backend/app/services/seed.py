import gzip
import json
from pathlib import Path
from typing import Dict, Any, Tuple
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Chunk, Document

def export_seed(db: Session, out_path: Path) -> int:
    """
    Export all chunks and documents with embeddings to a gzip-compressed JSONL file.
    Includes a metadata header with EMBED_MODEL and EMBED_DIM.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    docs = db.query(Document).all()
    chunks = db.query(Chunk).all()

    header = {
        "type": "header",
        "app": "Edukonic_RAG_QP",
        "embed_model": settings.EMBED_MODEL,
        "embed_dim": settings.EMBED_DIM,
        "doc_count": len(docs),
        "chunk_count": len(chunks)
    }

    with gzip.open(out_path, "wt", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")

        # Write documents
        for d in docs:
            d_row = {
                "type": "document",
                "id": d.id,
                "class": d.class_num,
                "subject": d.subject,
                "chapter_no": d.chapter_no,
                "chapter_title": d.chapter_title,
                "edition_year": d.edition_year,
                "source_file": d.source_file,
                "page_count": d.page_count,
                "status": d.status,
            }
            f.write(json.dumps(d_row) + "\n")

        # Write chunks
        for c in chunks:
            c_row = {
                "type": "chunk",
                "id": c.id,
                "document_id": c.document_id,
                "chapter_no": c.chapter_no,
                "page_start": c.page_start,
                "page_end": c.page_end,
                "section_heading": c.section_heading,
                "content_type": c.content_type,
                "token_count": c.token_count,
                "text": c.text,
                "embedding": list(c.embedding) if c.embedding is not None else None,
            }
            f.write(json.dumps(c_row) + "\n")

    return len(chunks)

def import_seed(db: Session, seed_file: Path) -> Tuple[int, int]:
    """
    Import documents and chunks from a seed file.
    Refuses if EMBED_MODEL or EMBED_DIM in the file header differ from current settings.
    """
    if not seed_file.exists():
        raise FileNotFoundError(f"Seed file not found: {seed_file}")

    opener = gzip.open if seed_file.name.endswith(".gz") else open

    imported_docs = 0
    imported_chunks = 0

    with opener(seed_file, "rt", encoding="utf-8") as f:
        first_line = f.readline()
        if not first_line:
            raise ValueError("Seed file is empty")

        header = json.loads(first_line)
        if header.get("type") != "header":
            raise ValueError("Invalid seed file: missing header")

        file_model = header.get("embed_model")
        file_dim = header.get("embed_dim")

        if file_model != settings.EMBED_MODEL:
            raise ValueError(
                f"Embedding model mismatch! Seed file uses '{file_model}', but .env is configured with '{settings.EMBED_MODEL}'."
            )
        if file_dim != settings.EMBED_DIM:
            raise ValueError(
                f"Embedding dimension mismatch! Seed file uses {file_dim}, but .env is configured with {settings.EMBED_DIM}."
            )

        doc_id_map = {}

        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            item_type = item.get("type")

            if item_type == "document":
                # Check if exists
                existing = db.query(Document).filter(
                    Document.class_num == item.get("class", 10),
                    Document.subject == item.get("subject", "Science"),
                    Document.chapter_no == item["chapter_no"],
                    Document.edition_year == item.get("edition_year", 2026)
                ).first()

                if not existing:
                    doc = Document(
                        class_num=item.get("class", 10),
                        subject=item.get("subject", "Science"),
                        chapter_no=item["chapter_no"],
                        chapter_title=item["chapter_title"],
                        edition_year=item.get("edition_year", 2026),
                        source_file=item["source_file"],
                        page_count=item.get("page_count", 0),
                        status=item.get("status", "ready"),
                    )
                    db.add(doc)
                    db.commit()
                    db.refresh(doc)
                    doc_id_map[item["id"]] = doc.id
                    imported_docs += 1
                else:
                    doc_id_map[item["id"]] = existing.id

            elif item_type == "chunk":
                orig_doc_id = item["document_id"]
                mapped_doc_id = doc_id_map.get(orig_doc_id)
                if not mapped_doc_id:
                    # Fallback find by chapter
                    doc_match = db.query(Document).filter(Document.chapter_no == item["chapter_no"]).first()
                    mapped_doc_id = doc_match.id if doc_match else None

                if mapped_doc_id:
                    # Check chunk exists by text hash/prefix
                    exists = db.query(Chunk).filter(
                        Chunk.chapter_no == item["chapter_no"],
                        Chunk.page_start == item["page_start"],
                        Chunk.text == item["text"]
                    ).first()

                    if not exists:
                        chunk = Chunk(
                            document_id=mapped_doc_id,
                            chapter_no=item["chapter_no"],
                            page_start=item["page_start"],
                            page_end=item["page_end"],
                            section_heading=item.get("section_heading"),
                            content_type=item["content_type"],
                            text=item["text"],
                            token_count=item.get("token_count", 0),
                            embedding=item.get("embedding"),
                        )
                        db.add(chunk)
                        imported_chunks += 1

        db.commit()

    return imported_docs, imported_chunks
