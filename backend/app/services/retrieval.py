from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import Chunk, Document
from app.services.llm import embed_one

def search_chunks(
    query: str,
    db: Session,
    chapter_no: Optional[int] = None,
    k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Search top-k chunks by cosine similarity using BGE query prefix and pgvector.
    Cosine score = 1.0 - cosine_distance.
    """
    # Generate normalized query vector with BGE search prefix
    query_vector = embed_one(query, is_query=True)

    # pgvector cosine distance operator <=>
    # cosine_distance = Chunk.embedding.cosine_distance(query_vector)
    dist_expr = Chunk.embedding.cosine_distance(query_vector)

    stmt = select(Chunk, dist_expr.label("distance"))
    if chapter_no is not None:
        stmt = stmt.where(Chunk.chapter_no == chapter_no)

    stmt = stmt.order_by(dist_expr.asc()).limit(k)
    results = db.execute(stmt).all()

    hits = []
    for chunk, distance in results:
        score = 1.0 - float(distance) if distance is not None else 0.0
        hits.append({
            "id": chunk.id,
            "chapter_no": chunk.chapter_no,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "pages": f"p.{chunk.page_start}-{chunk.page_end}",
            "section_heading": chunk.section_heading,
            "content_type": chunk.content_type,
            "token_count": chunk.token_count,
            "score": round(score, 4),
            "distance": round(float(distance), 4) if distance is not None else 0.0,
            "snippet": chunk.text[:180].replace("\n", " ").strip() + "...",
            "text": chunk.text,
        })

    return hits
