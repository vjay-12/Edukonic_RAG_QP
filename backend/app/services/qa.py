import re
import random
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select, func
import numpy as np

from app.config import settings
from app.models import Document, Chunk

def detect_suspicious_text(text: str) -> List[str]:
    """Flag text for suspicious patterns: mojibake, long runs of symbols, repeated lines."""
    flags = []
    # Mojibake or unprintable characters
    if "\ufffd" in text:
        flags.append("mojibake_char")
    # Long run of non-alphanumeric, non-markdown symbols
    if re.search(r'[^a-zA-Z0-9\s\-_=|\*#<>\.\,\:\;\(\)\[\]\/]{8,}', text):
        flags.append("long_symbol_run")
    # Repeated identical lines (excluding short ones and markdown bullets/tags)
    lines = [
        l.strip() for l in text.split("\n")
        if len(l.strip()) > 30 and not l.strip().startswith(("-", "*", "#", "<", "|", "<!--"))
    ]
    if len(lines) > 3 and len(lines) != len(set(lines)):
        flags.append("repeated_lines")
    return flags

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    """Compute cosine similarity between two normalized vectors."""
    dot = sum(a * b for a, b in zip(v1, v2))
    return float(dot)

def generate_qa_report(chapter_no: int, db: Session, out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Generate chunk QA report and verify gate conditions for a chapter."""
    doc = db.query(Document).filter(Document.chapter_no == chapter_no).first()
    if not doc:
        raise ValueError(f"Document for chapter {chapter_no} not found in database.")

    chunks = db.query(Chunk).filter(Chunk.chapter_no == chapter_no).order_by(Chunk.id).all()
    if not chunks:
        raise ValueError(f"No chunks found for chapter {chapter_no}.")

    total_chunks = len(chunks)
    token_counts = [c.token_count for c in chunks]
    avg_tokens = sum(token_counts) / total_chunks
    max_tokens = max(token_counts)
    min_tokens = min(token_counts)

    # Token histogram
    bins = {"<100": 0, "100-250": 0, "250-400": 0, "400-480": 0, ">480": 0}
    for tc in token_counts:
        if tc < 100:
            bins["<100"] += 1
        elif tc <= 250:
            bins["100-250"] += 1
        elif tc <= 400:
            bins["250-400"] += 1
        elif tc <= 480:
            bins["400-480"] += 1
        else:
            bins[">480"] += 1

    # Page coverage
    covered_pages = set()
    for c in chunks:
        for p in range(c.page_start, c.page_end + 1):
            covered_pages.add(p)
    total_pages = doc.page_count
    # Ignore cover/blank pages: pages with chunks vs total doc pages
    page_coverage_pct = (len(covered_pages) / total_pages * 100.0) if total_pages > 0 else 0.0

    # Anomalies
    chunks_under_40 = [c for c in chunks if c.token_count < 40]
    chunks_over_max = [c for c in chunks if c.token_count > settings.CHUNK_MAX_TOKENS]
    empty_chunks = [c for c in chunks if not c.text.strip()]
    no_page_chunks = [c for c in chunks if not c.page_start or not c.page_end]

    # Suspicious text check
    garbled_chunks = []
    for c in chunks:
        flags = detect_suspicious_text(c.text)
        if flags:
            garbled_chunks.append((c.id, flags))

    # Near-duplicate check (cosine similarity > 0.97)
    near_duplicates = []
    for i in range(total_chunks):
        for j in range(i + 1, total_chunks):
            sim = cosine_similarity(chunks[i].embedding, chunks[j].embedding)
            if sim > 0.97:
                near_duplicates.append((chunks[i].id, chunks[j].id, round(sim, 4)))

    # Content type distribution
    content_types: Dict[str, int] = {}
    for c in chunks:
        content_types[c.content_type] = content_types.get(c.content_type, 0) + 1

    # Sample 10 random chunks for review (deterministic seed based on chapter)
    rng = random.Random(chapter_no + 42)
    sample_size = min(10, total_chunks)
    sampled_chunks = rng.sample(chunks, sample_size)

    # Evaluate Quality Gate
    pct_under_40 = (len(chunks_under_40) / total_chunks) * 100.0
    pct_garbled = (len(garbled_chunks) / total_chunks) * 100.0

    gate_coverage = page_coverage_pct >= 98.0
    gate_empty = len(empty_chunks) == 0
    gate_under_40 = pct_under_40 < 3.0
    gate_garbled = pct_garbled < 1.0
    gate_passed = gate_coverage and gate_empty and gate_under_40 and gate_garbled

    report_data = {
        "chapter_no": chapter_no,
        "chapter_title": doc.chapter_title,
        "total_chunks": total_chunks,
        "total_pages": total_pages,
        "covered_pages_count": len(covered_pages),
        "page_coverage_pct": round(page_coverage_pct, 2),
        "token_stats": {
            "min": min_tokens,
            "max": max_tokens,
            "avg": round(avg_tokens, 1),
            "histogram": bins,
        },
        "anomalies": {
            "under_40_count": len(chunks_under_40),
            "under_40_pct": round(pct_under_40, 2),
            "over_max_count": len(chunks_over_max),
            "empty_count": len(empty_chunks),
            "no_page_count": len(no_page_chunks),
            "garbled_count": len(garbled_chunks),
            "garbled_pct": round(pct_garbled, 2),
        },
        "near_duplicates": near_duplicates,
        "content_types": content_types,
        "sampled_chunks": [
            {
                "id": c.id,
                "pages": f"p.{c.page_start}-{c.page_end}",
                "type": c.content_type,
                "tokens": c.token_count,
                "heading": c.section_heading,
                "text": c.text,
            }
            for c in sampled_chunks
        ],
        "gate": {
            "passed": gate_passed,
            "page_coverage_passed": gate_coverage,
            "no_empty_passed": gate_empty,
            "under_40_passed": gate_under_40,
            "garbled_passed": gate_garbled,
        }
    }

    # Generate Markdown report
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        md_file = out_dir / f"chunks_ch{chapter_no:02d}.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(f"# Chunk QA Report — Chapter {chapter_no}: {doc.chapter_title}\n\n")
            f.write(f"**Gate Status**: {'PASSED [OK]' if gate_passed else 'FAILED [ACTION REQUIRED]'}\n\n")
            f.write("## Overview\n")
            f.write(f"- **Total Chunks**: {total_chunks}\n")
            f.write(f"- **Page Coverage**: {page_coverage_pct:.1f}% ({len(covered_pages)}/{total_pages} pages)\n")
            f.write(f"- **Tokens**: Min {min_tokens}, Max {max_tokens}, Avg {avg_tokens:.1f}\n")
            f.write(f"- **Token Histogram**: {bins}\n\n")
            f.write("## Content Types\n")
            for ct, cnt in content_types.items():
                f.write(f"- {ct}: {cnt} ({cnt/total_chunks*100:.1f}%)\n")
            f.write("\n## Quality Gate Checklist\n")
            f.write(f"- [{'x' if gate_coverage else ' '}] Page coverage >= 98% (Current: {page_coverage_pct:.1f}%)\n")
            f.write(f"- [{'x' if gate_empty else ' '}] No empty chunks (Current: {len(empty_chunks)})\n")
            f.write(f"- [{'x' if gate_under_40 else ' '}] Chunks < 40 tokens < 3% (Current: {pct_under_40:.1f}%)\n")
            f.write(f"- [{'x' if gate_garbled else ' '}] Garbled chunks < 1% (Current: {pct_garbled:.1f}%)\n\n")
            if near_duplicates:
                f.write(f"## Near-Duplicate Chunks (>0.97 Cosine)\n")
                for c1, c2, sim in near_duplicates:
                    f.write(f"- Chunk #{c1} & Chunk #{c2} (similarity: {sim})\n")
                f.write("\n")
            f.write("## Sample Chunks for Manual Sign-off\n\n")
            for sc in report_data["sampled_chunks"]:
                f.write(f"### Chunk #{sc['id']} [{sc['pages']}] [{sc['type']}] ({sc['tokens']} tokens)\n")
                f.write(f"**Section**: {sc['heading']}\n\n")
                f.write(f"```text\n{sc['text']}\n```\n\n")

    return report_data
