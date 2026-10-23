import os
import sys
import random

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.db import SessionLocal
from app.models import Chunk
from app.services.retrieval import search_chunks

def main():
    queries = [
        "Ohm's law",
        "balancing a chemical equation",
        "double circulation in humans",
        "resistors connected in parallel",
        "aerobic and anaerobic respiration"
    ]

    print("==================================================")
    print("           5 PILOT RETRIEVAL SEARCH TESTS         ")
    print("==================================================")

    with SessionLocal() as db:
        for q in queries:
            print(f"\nQuery: '{q}'")
            hits = search_chunks(q, db, k=3)
            for i, h in enumerate(hits):
                print(f"  [{i+1}] Score: {h['score']:.4f} | Chapter {h['chapter_no']} ({h['pages']}) | [{h['content_type'].upper()}] {h['section_heading']}")
                clean_snip = h['snippet'].replace('\n', ' ')
                print(f"      Snippet: {clean_snip[:110]}...")

        print("\n==================================================")
        print("    5 RANDOM CHUNKS PER CHAPTER FOR SIGN-OFF      ")
        print("==================================================")

        for ch in [1, 5, 11]:
            chunks = db.query(Chunk).filter(Chunk.chapter_no == ch).order_by(Chunk.id).all()
            rng = random.Random(ch * 100 + 7)
            sample = rng.sample(chunks, min(5, len(chunks)))

            print(f"\n---------------- CHAPTER {ch} SAMPLES ----------------")
            for c in sample:
                print(f"\n[Chunk #{c.id} | Ch {c.chapter_no} | {c.page_start}-{c.page_end} | {c.content_type} | {c.token_count} tokens]")
                print(f"Heading: {c.section_heading}")
                print(f"Content:\n{c.text.strip()}\n")

if __name__ == "__main__":
    main()
