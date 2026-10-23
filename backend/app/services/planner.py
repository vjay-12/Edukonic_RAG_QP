import math
from typing import List, Dict, Any
from app.schemas import PaperConfig

def allocate_counts_largest_remainder(total: int, weights: Dict[Any, float]) -> Dict[Any, int]:
    """Allocate an integer total across items according to weights using Largest Remainder (Hare-Niemeyer)."""
    if total <= 0:
        return {k: 0 for k in weights}

    # Normalize weights
    weight_sum = sum(weights.values())
    if weight_sum <= 0:
        weight_sum = 1.0

    floors = {}
    remainders = []

    for k, w in weights.items():
        exact = total * (w / weight_sum)
        fl = int(math.floor(exact))
        floors[k] = fl
        remainders.append((exact - fl, k))

    allocated = sum(floors.values())
    leftover = total - allocated

    # Sort descending by remainder
    remainders.sort(key=lambda x: x[0], reverse=True)

    for i in range(leftover):
        k = remainders[i % len(remainders)][1]
        floors[k] += 1

    return floors

def plan_paper_slots(config: PaperConfig) -> List[Dict[str, Any]]:
    """
    Expand a PaperConfig into an ordered list of question slots:
    (slot_no, section, type, marks, chapter_no, difficulty, competency, bloom_hint).
    Uses largest-remainder rounding to match chapter weights, difficulty mix, and competency targets.
    """
    raw_slots: List[Dict[str, Any]] = []
    slot_no = 1

    for sec in config.sections:
        for _ in range(sec.count):
            raw_slots.append({
                "slot_no": slot_no,
                "section": sec.id,
                "type": sec.type,
                "marks": sec.marks,
            })
            slot_no += 1

    total_questions = len(raw_slots)
    if total_questions == 0:
        return []

    # 1. Allocate chapters by weight
    ch_weights = {ch.chapter_no: ch.weight for ch in config.chapters}
    ch_counts = allocate_counts_largest_remainder(total_questions, ch_weights)

    # Distribute chapter assignments across sections evenly
    ch_pool = []
    for ch_no, count in ch_counts.items():
        ch_pool.extend([ch_no] * count)

    # Round-robin interleaved assignment
    # Sort pool so we spread chapters across the slots
    interleaved_chapters = []
    unique_chapters = sorted(ch_counts.keys())
    while ch_pool:
        for ch in unique_chapters:
            if ch in ch_pool:
                interleaved_chapters.append(ch)
                ch_pool.remove(ch)

    for idx, slot in enumerate(raw_slots):
        slot["chapter_no"] = interleaved_chapters[idx]

    # 2. Allocate difficulty mix
    diff_counts = allocate_counts_largest_remainder(total_questions, config.difficulty_mix)
    diff_pool = []
    for d, c in diff_counts.items():
        diff_pool.extend([d] * c)

    # Heuristic: 1-mark questions bias towards easy/medium; 5-mark bias towards medium/hard
    # Sort slots by marks, sort diff pool accordingly
    sorted_slot_indices = sorted(range(total_questions), key=lambda i: raw_slots[i]["marks"])
    diff_order = {"easy": 1, "medium": 2, "hard": 3}
    diff_pool.sort(key=lambda d: diff_order.get(d, 2))

    for rank, orig_idx in enumerate(sorted_slot_indices):
        raw_slots[orig_idx]["difficulty"] = diff_pool[rank]

    # 3. Allocate competency questions
    comp_target = round(total_questions * (config.competency_percent / 100.0))
    # Case based is always competency
    for s in raw_slots:
        s["competency"] = False

    comp_assigned = 0
    for s in raw_slots:
        if s["type"] == "case" and comp_assigned < comp_target:
            s["competency"] = True
            comp_assigned += 1

    # Remaining competency slots distributed to other sections
    if comp_assigned < comp_target:
        for s in raw_slots:
            if not s["competency"] and s["type"] in ["mcq", "sa", "vsa"]:
                s["competency"] = True
                comp_assigned += 1
                if comp_assigned >= comp_target:
                    break

    # 4. Allocate bloom taxonomy hints
    for s in raw_slots:
        diff = s.get("difficulty", "medium")
        is_comp = s.get("competency", False)
        if s["type"] == "case":
            s["bloom_hint"] = "analyze"
        elif is_comp:
            s["bloom_hint"] = "apply" if diff == "easy" else "analyze"
        elif diff == "easy":
            s["bloom_hint"] = "remember"
        elif diff == "medium":
            s["bloom_hint"] = "understand"
        else:
            s["bloom_hint"] = "evaluate"

    return raw_slots

def compute_blueprint_report(slots: List[Dict[str, Any]], questions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate summary blueprint metrics comparing generated questions to the plan."""
    marks_by_chapter: Dict[int, int] = {}
    count_by_type: Dict[str, int] = {}
    diff_split: Dict[str, int] = {"easy": 0, "medium": 0, "hard": 0}
    comp_count = 0
    total_marks = 0
    flagged_count = 0

    for q in questions:
        ch = q.get("chapter_no", 1)
        m = q.get("marks", 0)
        t = q.get("type", "unknown")
        d = q.get("difficulty", "medium")
        c = q.get("competency", False)
        val = q.get("validation", {})

        marks_by_chapter[ch] = marks_by_chapter.get(ch, 0) + m
        count_by_type[t] = count_by_type.get(t, 0) + 1
        diff_split[d] = diff_split.get(d, 0) + 1
        if c:
            comp_count += 1
        total_marks += m

        verdict = val.get("verdict", "pass") if isinstance(val, dict) else "pass"
        if verdict in ["warn", "fail"]:
            flagged_count += 1

    total_q = len(questions)
    comp_pct = round((comp_count / total_q * 100.0), 1) if total_q > 0 else 0.0

    return {
        "total_marks": total_marks,
        "question_count": total_q,
        "marks_by_chapter": marks_by_chapter,
        "count_by_type": count_by_type,
        "difficulty_split": diff_split,
        "competency_count": comp_count,
        "competency_percent": comp_pct,
        "flagged_count": flagged_count,
    }
