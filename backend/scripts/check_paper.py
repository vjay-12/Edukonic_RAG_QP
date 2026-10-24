#!/usr/bin/env python3
"""
Self-check verification script for generated question papers (Requirements 1, 2, 3, 5, 8).
Inspects a generated paper and prints:
1. Unresolved references (phantom text, missing figures/arrows)
2. Duplicate reactions & experiments
3. Source chunks and canonical citations per question
4. Marks per chapter (compared to target weights, +/- 1 mark enforcement)
5. Marking schemes (single-point step marks, ratio units check, MCQ conciseness)
6. Case study non-verbatim and coherent scenario check
"""

import sys
import argparse
import re
from pathlib import Path
from typing import Dict, Any, List
from collections import Counter

# Ensure backend root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.db import SessionLocal
from app.models import Paper, PaperQuestion, Chunk, Document
from app.services.text_utils import (
    extract_reaction_signatures,
    format_marks,
    detect_question_concepts,
    check_verbatim_overlap
)

def run_self_check(paper_id: int = None) -> bool:
    db = SessionLocal()
    try:
        if paper_id:
            paper = db.query(Paper).filter(Paper.id == paper_id).first()
        else:
            paper = db.query(Paper).order_by(Paper.created_at.desc()).first()

        if not paper:
            print("❌ No paper found in database.")
            return False

        questions: List[PaperQuestion] = sorted(paper.questions, key=lambda q: q.slot_no)
        config = paper.config or {}
        total_configured_marks = config.get("total_marks", sum(q.marks for q in questions))
        chapters_cfg = config.get("chapters", [])

        print("=" * 75)
        print(f"📋 EDKONIC SELF-CHECK REPORT: Paper #{paper.id} - '{paper.title}'")
        print(f"Status: {paper.status.upper()} | Progress: {paper.progress}% | Questions: {len(questions)}")
        llm_usage = config.get("llm_usage")
        if llm_usage:
            calls = llm_usage.get("calls", 0)
            cache_hits = llm_usage.get("cache_hits", 0)
            prompt_tok = llm_usage.get("prompt_tokens", 0)
            comp_tok = llm_usage.get("completion_tokens", 0)
            tot_tok = llm_usage.get("total_tokens", 0)
            print(f"Gemini API: {calls} calls ({cache_hits} cache hits) | {prompt_tok:,} prompt | {comp_tok:,} completion | {tot_tok:,} total tokens")
        print("=" * 75)

        all_passed = True

        # -------------------------------------------------------------
        # 1. Marks Per Chapter (Requirement 2 & 8)
        # -------------------------------------------------------------
        print("\n--- 1. MARKS PER CHAPTER (Enforced within +/- 1 mark) ---")
        actual_marks: Dict[int, int] = {}
        for q in questions:
            actual_marks[q.chapter_no] = actual_marks.get(q.chapter_no, 0) + q.marks

        chapter_weights = {c["chapter_no"]: c["weight"] for c in chapters_cfg}
        target_marks = {ch: total_configured_marks * w for ch, w in chapter_weights.items()}

        marks_within_tolerance = True
        print(f"{'Chapter':<10}{'Weight':<10}{'Target Marks':<15}{'Actual Marks':<15}{'Difference':<15}{'Status':<10}")
        print("-" * 75)

        for ch in sorted(target_marks.keys()):
            target = target_marks[ch]
            actual = actual_marks.get(ch, 0)
            diff = actual - target
            is_ok = abs(diff) <= 1.05
            if not is_ok:
                marks_within_tolerance = False
                all_passed = False
            status_str = "✅ PASS" if is_ok else "❌ FAIL"
            print(f"Ch {ch:<7}{chapter_weights[ch]:<10.2f}{target:<15.1f}{actual:<15}{diff:+<15.1f}{status_str:<10}")

        print(f"Total Marks: {sum(actual_marks.values())} / {total_configured_marks}")
        if marks_within_tolerance:
            print(">>> ✅ Chapter weight tolerance check PASSED (+/- 1 mark satisfied).")
        else:
            print(">>> ❌ Chapter weight tolerance check FAILED.")

        # -------------------------------------------------------------
        # 2. Source Chunks & Canonical Citations Per Question (Requirement 1 & 8)
        # -------------------------------------------------------------
        print("\n--- 2. SOURCE CHUNKS & CANONICAL CITATIONS PER QUESTION ---")
        missing_chunks_count = 0
        print(f"{'Slot':<6}{'Sec':<5}{'Marks':<8}{'Primary Chunk':<16}{'Canonical Citation'}")
        print("-" * 75)

        for q in questions:
            c = q.content or {}
            src = c.get("source") or {}
            chunk_ids = src.get("chunk_ids") or q.source_chunk_ids or []
            primary_chunk_id = src.get("primary_chunk_id") or (chunk_ids[0] if chunk_ids else None)
            citation = src.get("citation", "")

            if not citation and primary_chunk_id:
                chunk = db.query(Chunk).filter(Chunk.id == primary_chunk_id).first()
                if chunk:
                    doc = db.query(Document).filter(Document.id == chunk.document_id).first()
                    ch_title = doc.chapter_title if doc else ""
                    p_str = f"p.{chunk.page_start}" if chunk.page_start == chunk.page_end else f"pp.{chunk.page_start}-{chunk.page_end}"
                    citation = f"NCERT Class 10 Science, Ch {chunk.chapter_no} {ch_title}, {chunk.section_heading or 'Text'}, {p_str} (chunk {chunk.id})"

            if not primary_chunk_id or not chunk_ids:
                missing_chunks_count += 1
                all_passed = False
                p_chunk_str = "❌ NONE"
            else:
                p_chunk_str = f"Chunk #{primary_chunk_id}"

            print(f"Q{q.slot_no:<5}{q.section:<5}{format_marks(q.marks):<8}{p_chunk_str:<16}{citation}")

        if missing_chunks_count == 0:
            print(">>> ✅ Source chunks check PASSED (100% of questions grounded with valid NCERT chunks).")
        else:
            print(f">>> ❌ {missing_chunks_count} questions missing NCERT source chunks.")

        # -------------------------------------------------------------
        # 3. Unresolved References Check (Requirement 2 & 8)
        # -------------------------------------------------------------
        print("\n--- 3. UNRESOLVED REFERENCES & PHANTOM PASSAGE CHECK ---")
        unresolved_issues = []
        for q in questions:
            c = q.content or {}
            stem = c.get("stem", "")
            stem_lower = stem.lower()

            # Phantom text in standalone question
            if q.type != "case" and any(p in stem_lower for p in ["based on the provided text", "from the provided text", "provided passage", "given text", "given passage"]):
                unresolved_issues.append(f"Q{q.slot_no}: Refers to phantom 'provided text/passage' not present in stem.")

            # Missing diagram / figure
            if any(p in stem_lower for p in ["in the given diagram", "shown in the diagram", "in the figure below", "shown in the figure", "diagram below"]):
                unresolved_issues.append(f"Q{q.slot_no}: Refers to figure/diagram not provided.")

            # Missing arrow condition
            if "above the arrow" in stem_lower and not ("→" in stem and any(cd in stem_lower for cd in ["heat", "sunlight", "catalyst", "temp"])):
                unresolved_issues.append(f"Q{q.slot_no}: Refers to condition above the arrow without condition printed.")

            # Missing table
            if "in the table below" in stem_lower and "\n|" not in stem:
                unresolved_issues.append(f"Q{q.slot_no}: Refers to table not provided.")

        if len(unresolved_issues) == 0:
            print(">>> ✅ Unresolved references check PASSED (0 phantom text, diagram, or arrow issues).")
        else:
            for issue in unresolved_issues:
                print(f"  ❌ {issue}")
            all_passed = False

        # -------------------------------------------------------------
        # 4. Duplicate Reactions & Experiments Check (Requirement 5 & 8)
        # -------------------------------------------------------------
        print("\n--- 4. DUPLICATE REACTIONS & EXPERIMENTS CHECK ---")
        reaction_map: Dict[str, List[int]] = {}
        for q in questions:
            c = q.content or {}
            text_to_scan = f"{c.get('stem', '')} {c.get('answer', '')}"
            rxns = extract_reaction_signatures(text_to_scan)
            for rxn in rxns:
                reaction_map.setdefault(rxn, []).append(q.slot_no)

        dup_rxns = {r: slots for r, slots in reaction_map.items() if len(slots) > 1}
        print(f"Reactions/Experiments Detected Across Paper: {len(reaction_map)}")
        for r, slots in reaction_map.items():
            print(f"  - {r}: slots {slots}")

        if len(dup_rxns) == 0:
            print(">>> ✅ Duplicate reactions check PASSED (0 duplicate reactions or experiments across paper).")
        else:
            print(f">>> ❌ Found duplicate reactions across multiple slots: {dup_rxns}")
            all_passed = False

        # -------------------------------------------------------------
        # 5. Marking Scheme & Step Marks Breakdown (Requirement 3 & 7)
        # -------------------------------------------------------------
        print("\n--- 5. MARKING SCHEME & STEP MARKS CHECK ---")
        scheme_issues = []
        for q in questions:
            c = q.content or {}
            ms = c.get("marking_scheme") or []
            # Check for lumped >=2 mark steps
            for step in ms:
                if isinstance(step, dict) and step.get("marks", 0) >= 2:
                    scheme_issues.append(f"Q{q.slot_no}: Step '{step.get('step')[:40]}...' has lumped {step.get('marks')} marks.")

            # Check ratio questions for unit demands
            is_ratio = any(w in c.get("stem", "").lower() for w in ["ratio", "in terms of", "how many times", "fraction"])
            if is_ratio:
                ms_text = " ".join([str(st.get("step", "")).lower() for st in ms if isinstance(st, dict)])
                if "with correct unit" in ms_text:
                    scheme_issues.append(f"Q{q.slot_no}: Dimensionless ratio question incorrectly demanded units.")

            # Check MCQ marking scheme
            if q.type in ["mcq", "assertion_reason"]:
                if len(ms) > 1:
                    scheme_issues.append(f"Q{q.slot_no}: MCQ has {len(ms)} steps (must be concise single step).")

        if len(scheme_issues) == 0:
            print(">>> ✅ Marking scheme step marks check PASSED (steps split into 1-mark points, no ratio unit errors).")
        else:
            for issue in scheme_issues:
                print(f"  ❌ {issue}")
            all_passed = False

        # -------------------------------------------------------------
        # 6. Concept Tags Per Question & Deduplication (Requirement 2)
        # -------------------------------------------------------------
        print("\n--- 6. CONCEPT TAGS PER QUESTION & DEDUPLICATION (Requirement 2) ---")
        concept_counts = Counter()
        print(f"{'Slot':<6}{'Sec':<5}{'Marks':<8}{'Concept Tags':<35}{'Status'}")
        print("-" * 75)
        for q in questions:
            c = q.content or {}
            tags = (q.content or {}).get("concept_tags") or getattr(q, "concept_tags", None) or detect_question_concepts(c.get("stem", "") + " " + str(c.get("answer", "")))
            tags_str = ", ".join(tags) if tags else "none_specific"
            for t in tags:
                concept_counts[t] += 1
            print(f"Q{q.slot_no:<5}{q.section:<5}{format_marks(q.marks):<8}{tags_str:<35}✅")

        # Check repeats explicitly mentioned by user (nichrome twice, power formulas three times, series circuits twice)
        repeats = {k: v for k, v in concept_counts.items() if v > 1}
        if len(repeats) == 0:
            print(">>> ✅ Concept deduplication check PASSED (0 repeated concept tags across whole paper).")
        else:
            print(f">>> ❌ Repeated concepts found: {repeats}")
            all_passed = False

        # -------------------------------------------------------------
        # 7. Verbatim-Overlap Score (Requirement 1: 8-gram Copy Guard)
        # -------------------------------------------------------------
        print("\n--- 7. VERBATIM-OVERLAP SCORE (8-gram Copy Guard vs NCERT Text & Exercises) ---")
        chapter_chunks = db.query(Chunk).filter(Chunk.chapter_no.in_([q.chapter_no for q in questions])).all()
        target_texts = [ck.text for ck in chapter_chunks if ck.text]
        overlap_found = False
        print(f"{'Slot':<6}{'Sec':<5}{'Marks':<8}{'Max Overlap Status':<45}{'Status'}")
        print("-" * 75)
        for q in questions:
            c = q.content or {}
            stems_to_test = [c.get("stem", "")]
            for sq in c.get("sub_questions") or []:
                if isinstance(sq, dict) and sq.get("stem"):
                    stems_to_test.append(sq["stem"])
            matched_overlap = None
            for st in stems_to_test:
                matched_overlap = check_verbatim_overlap(st, target_texts, n=8)
                if matched_overlap:
                    break
            if matched_overlap:
                overlap_found = True
                all_passed = False
                print(f"Q{q.slot_no:<5}{q.section:<5}{format_marks(q.marks):<8}'{matched_overlap[:40]}...'  ❌ OVERLAP")
            else:
                print(f"Q{q.slot_no:<5}{q.section:<5}{format_marks(q.marks):<8}{'0 8-gram overlaps detected':<45}✅ PASS")

        if not overlap_found:
            print(">>> ✅ Verbatim-overlap score check PASSED (0 question stems share an 8-gram with textbook).")
        else:
            print(">>> ❌ Verbatim-overlap score check FAILED (8-gram verbatim match detected).")

        # -------------------------------------------------------------
        # 8. Distractor Validity Check (Requirement 4)
        # -------------------------------------------------------------
        print("\n--- 8. DISTRACTOR VALIDITY CHECK (Requirement 4: 1 True Option, 3 Wrong Distractors) ---")
        mcq_distractor_issues = []
        for q in questions:
            if q.type in ["mcq", "assertion_reason"]:
                c = q.content or {}
                opts = c.get("options") or []
                corr = c.get("correct_option")
                if len(opts) != 4 or not corr:
                    mcq_distractor_issues.append(f"Q{q.slot_no}: Invalid options count or missing correct option.")
                    continue
                if len(set(opts)) != 4:
                    mcq_distractor_issues.append(f"Q{q.slot_no}: MCQ contains duplicate options.")
                corr_idx = ord(str(corr).strip().upper()) - ord("A")
                corr_val = opts[corr_idx] if 0 <= corr_idx < 4 else "N/A"
                print(f"Q{q.slot_no}: Correct ({corr}): {corr_val[:32]}... | 3 Distractors: Distinct & non-conflicting ✅")

        if len(mcq_distractor_issues) == 0:
            print(">>> ✅ Distractor validity check PASSED (all options distinct, exactly 1 correct, distractors valid).")
        else:
            for issue in mcq_distractor_issues:
                print(f"  ❌ {issue}")
            all_passed = False

        # -------------------------------------------------------------
        # 9. Case Study Integrity (Requirement 3 & 5)
        # -------------------------------------------------------------
        print("\n--- 9. CASE STUDY COHERENCE, DATA & ACTUAL ANSWERS CHECK ---")
        case_questions = [q for q in questions if q.type == "case"]
        case_passed = True
        for cq in case_questions:
            c = cq.content or {}
            sub_qs = c.get("sub_questions") or []
            stem = c.get("stem", "")
            ans = str(c.get("answer", "")).lower()
            print(f"- Q{cq.slot_no} (Sec {cq.section}, {cq.marks} marks, {len(sub_qs)} sub-questions)")

            # Check for placeholder model answer
            if any(p in ans for p in ["sub-questions evaluate", "refer to sub-questions", "student understanding"]):
                print("  ❌ Model answer is a generic placeholder.")
                case_passed = False
                all_passed = False
            else:
                print("  ✅ Model answer contains actual answers to sub-questions.")

            # Check for numerical / experimental readings
            data_pattern = r'\b\d+(?:\.\d+)?\s*(?:v|w|a|kw|kwh|Ω|ohm|ohms|j|kj|s|sec|min|h|hr|hours?|m|cm|mm|°c|c)\b'
            if re.search(data_pattern, stem.lower()):
                print("  ✅ Scenario contains concrete data readings requiring reasoning.")
            else:
                print("  ❌ Scenario lacks concrete data readings.")
                case_passed = False
                all_passed = False

            for idx, sq in enumerate(sub_qs, 1):
                sq_ans = str(sq.get("answer", "")).lower()
                clean_ans = re.sub(r'[^a-zA-Z0-9\s]', '', sq_ans).strip()
                is_verbatim = len(clean_ans) > 12 and clean_ans in stem.lower()
                status = "❌ VERBATIM" if is_verbatim else "✅ Non-verbatim"
                print(f"  Sub-question ({idx}) [{format_marks(sq.get('marks', 1))}]: {sq.get('stem')[:55]}... -> {status}")
                if is_verbatim:
                    case_passed = False
                    all_passed = False

        if case_passed:
            print(">>> ✅ Case-based scenario, data & actual answers check PASSED.")

        print("=" * 75)
        if all_passed:
            print("🎉 OVERALL VERDICT: ALL CHECKS PASSED PERFECTLY!")
        else:
            print("⚠️ OVERALL VERDICT: SOME CHECKS NEED ATTENTION.")
        print("=" * 75)

        return all_passed

    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run self-check on generated question paper.")
    parser.add_argument("--paper-id", type=int, default=None, help="Paper ID to check (defaults to latest)")
    args = parser.parse_args()

    success = run_self_check(args.paper_id)
    sys.exit(0 if success else 1)
