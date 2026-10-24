import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

sys.stdout.reconfigure(encoding='utf-8')

from app.db import SessionLocal
from app.models import Paper, PaperQuestion, Chunk

paper_id = int(sys.argv[1]) if len(sys.argv) > 1 else 6
slots = [int(x) for x in sys.argv[2].split(",")] if len(sys.argv) > 2 else list(range(1, 11))

db = SessionLocal()
paper = db.query(Paper).filter(Paper.id == paper_id).first()

print(f"=== PAPER #{paper.id}: {paper.title} ===")
questions = db.query(PaperQuestion).filter(PaperQuestion.paper_id == paper.id, PaperQuestion.slot_no.in_(slots)).order_by(PaperQuestion.slot_no).all()
for q in questions:
    c = json.loads(q.content) if isinstance(q.content, str) else q.content
    source = c.get("source", {})
    chunk_ids = q.source_chunk_ids or []
    print(f"\n==========================================")
    print(f"--- Q{q.slot_no} (Sec {q.section}, {q.type}, {q.marks}m, Ch {q.chapter_no}) ---")
    print(f"Topic: {q.topic}")
    print(f"Stem: {c.get('stem')}")
    if c.get("options"):
        print(f"Options: {c.get('options')}")
        print(f"Correct: {c.get('correct_option')}")
    if c.get("sub_questions"):
        print(f"Sub-questions: {c.get('sub_questions')}")
    print(f"Answer: {c.get('answer')}")
    print(f"Marking scheme: {c.get('marking_scheme')}")
    print(f"Source object: {source}")
    print(f"Source chunk IDs: {chunk_ids}")
    
    if chunk_ids:
        for cid in chunk_ids:
            chunk = db.query(Chunk).filter(Chunk.id == cid).first()
            if chunk:
                print(f"  > Chunk #{chunk.id}: Ch {chunk.chapter_no} | Heading: {chunk.section_heading} | pp.{chunk.page_start}-{chunk.page_end}")
                print(f"    Excerpt: {chunk.text[:300]}...")
