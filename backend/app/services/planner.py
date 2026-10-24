import math
from typing import List, Dict, Any, Optional
from app.schemas import PaperConfig

NUMERICAL_CHAPTERS = {11}  # Chapter 11: Electricity

def allocate_counts_largest_remainder(total: int, weights: Dict[Any, float]) -> Dict[Any, int]:
    """Allocate an integer total across items according to weights using Largest Remainder (Hare-Niemeyer)."""
    if total <= 0:
        return {k: 0 for k in weights}

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

    remainders.sort(key=lambda x: x[0], reverse=True)

    for i in range(leftover):
        k = remainders[i % len(remainders)][1]
        floors[k] += 1

    return floors

def solve_chapter_marks_allocation(
    slots: List[Dict[str, Any]],
    target_marks: Dict[int, float],
    numerical_chapter: Optional[int] = 11
) -> List[int]:
    """
    Assign a chapter to each slot such that:
    1. For every chapter, sum(marks) is within +/- 1.05 marks of target_marks.
    2. If numerical_chapter is in target_marks, at least one slot in Section C or D is assigned to it.
    3. Every chapter gets at least one question slot (if weight > 0).
    Uses constrained branch-and-bound search.
    """
    chapters = sorted(target_marks.keys())
    total_slots = len(slots)
    cd_indices = [i for i, s in enumerate(slots) if s["section"] in ["C", "D"]]

    best_assignment: Optional[List[int]] = None
    best_max_diff = float("inf")

    # Order slots: place Section C/D slots first to satisfy numerical constraint early
    ordered_indices = cd_indices + [i for i in range(total_slots) if i not in cd_indices]

    def search(order_pos: int, current_marks: Dict[int, int], current_counts: Dict[int, int], assignment: Dict[int, int]):
        nonlocal best_assignment, best_max_diff

        if order_pos == total_slots:
            # Check numerical constraint
            if numerical_chapter in chapters and cd_indices:
                has_num = any(assignment.get(i) == numerical_chapter for i in cd_indices)
                if not has_num:
                    return

            # Check that every chapter with target > 0 has at least 1 question
            for ch in chapters:
                if target_marks[ch] > 0 and current_counts[ch] == 0:
                    return

            # Check max diff
            max_diff = max(abs(current_marks[ch] - target_marks[ch]) for ch in chapters)
            if max_diff < best_max_diff:
                best_max_diff = max_diff
                best_assignment = [assignment[i] for i in range(total_slots)]
                if max_diff <= 1.0:
                    return True  # Found perfect match within +/- 1 mark
            return False

        slot_idx = ordered_indices[order_pos]
        slot = slots[slot_idx]
        m = slot["marks"]

        # Prioritize chapters that need marks the most
        # If in Section C/D and numerical_chapter hasn't been assigned yet, prioritize it!
        ch_candidates = list(chapters)
        if slot["section"] in ["C", "D"] and numerical_chapter in chapters:
            has_assigned_num = any(assignment.get(i) == numerical_chapter for i in cd_indices if i in assignment)
            if not has_assigned_num:
                ch_candidates.sort(key=lambda c: 0 if c == numerical_chapter else 1)
            else:
                ch_candidates.sort(key=lambda c: (current_marks[c] + m - target_marks[c]))
        else:
            ch_candidates.sort(key=lambda c: (current_marks[c] + m - target_marks[c]))

        for ch in ch_candidates:
            # Prune if this would overshoot target by more than 1.5 marks
            if current_marks[ch] + m > target_marks[ch] + 1.5:
                continue

            current_marks[ch] += m
            current_counts[ch] += 1
            assignment[slot_idx] = ch

            if search(order_pos + 1, current_marks, current_counts, assignment):
                return True

            del assignment[slot_idx]
            current_counts[ch] -= 1
            current_marks[ch] -= m

        return False

    current_marks = {ch: 0 for ch in chapters}
    current_counts = {ch: 0 for ch in chapters}
    assignment_dict: Dict[int, int] = {}
    found = search(0, current_marks, current_counts, assignment_dict)

    if best_assignment:
        return best_assignment

    # Fallback to largest remainder if constraint search didn't find complete fit
    ch_weights = {ch: target_marks[ch] for ch in chapters}
    ch_counts = allocate_counts_largest_remainder(total_slots, ch_weights)
    fallback = []
    for ch, cnt in ch_counts.items():
        fallback.extend([ch] * cnt)
    while len(fallback) < total_slots:
        fallback.append(chapters[0])
    return fallback[:total_slots]

def plan_paper_slots(config: PaperConfig) -> List[Dict[str, Any]]:
    """
    Expand a PaperConfig into an ordered list of question slots:
    (slot_no, section, type, marks, chapter_no, difficulty, competency, bloom_hint, is_numerical).
    Enforces chapter weights within +/- 1 mark and electricity numerical requirement.
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
                "is_numerical": False
            })
            slot_no += 1

    total_questions = len(raw_slots)
    if total_questions == 0:
        return []

    total_marks = config.total_marks or sum(s["marks"] for s in raw_slots)

    # 1. Allocate chapters by marks to enforce +/- 1 mark per chapter
    target_marks = {ch.chapter_no: total_marks * ch.weight for ch in config.chapters}
    assigned_chapters = solve_chapter_marks_allocation(
        slots=raw_slots,
        target_marks=target_marks,
        numerical_chapter=11 if 11 in target_marks else None
    )

    for idx, slot in enumerate(raw_slots):
        slot["chapter_no"] = assigned_chapters[idx]

    # 2. Electricity coverage: force at least one numerical in Section C or D
    if 11 in target_marks:
        num_candidates = [
            s for s in raw_slots
            if s["chapter_no"] == 11 and s["section"] in ["C", "D"]
        ]
        if num_candidates:
            # Tag the candidate with the highest marks (or first in C/D) as numerical
            num_slot = max(num_candidates, key=lambda s: s["marks"])
            num_slot["is_numerical"] = True
        else:
            # If no Ch 11 in C or D, find any Ch 11 slot in Section B, C, or D and tag it
            fallback_num = [s for s in raw_slots if s["chapter_no"] == 11 and s["marks"] >= 2]
            if fallback_num:
                fallback_num[0]["is_numerical"] = True

    # 3. Allocate difficulty mix
    diff_counts = allocate_counts_largest_remainder(total_questions, config.difficulty_mix)
    diff_pool = []
    for d, c in diff_counts.items():
        diff_pool.extend([d] * c)

    sorted_slot_indices = sorted(range(total_questions), key=lambda i: raw_slots[i]["marks"])
    diff_order = {"easy": 1, "medium": 2, "hard": 3}
    diff_pool.sort(key=lambda d: diff_order.get(d, 2))

    for rank, orig_idx in enumerate(sorted_slot_indices):
        raw_slots[orig_idx]["difficulty"] = diff_pool[rank]

    # 4. Allocate competency questions
    comp_target = round(total_questions * (config.competency_percent / 100.0))
    for s in raw_slots:
        s["competency"] = False

    comp_assigned = 0
    # Case based questions are always competency
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

    # 5. Allocate bloom taxonomy hints
    for s in raw_slots:
        diff = s.get("difficulty", "medium")
        is_comp = s.get("competency", False)
        if s["type"] == "case":
            s["bloom_hint"] = "analyze"
        elif s.get("is_numerical"):
            s["bloom_hint"] = "apply"
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
    numerical_count = 0
    concept_keys: List[str] = []
    duplicate_concept_keys: List[str] = []

    seen_keys = set()
    for q in questions:
        ch = q.get("chapter_no", 1)
        m = q.get("marks", 0)
        t = q.get("type", "unknown")
        d = q.get("difficulty", "medium")
        c = q.get("competency", False)
        val = q.get("validation", {})
        content = q.get("content", {})
        ck = content.get("concept_key") or q.get("concept_key") or ""
        is_num = content.get("is_numerical") or q.get("is_numerical") or False

        if ck:
            concept_keys.append(ck)
            if ck in seen_keys:
                duplicate_concept_keys.append(ck)
            seen_keys.add(ck)

        if is_num:
            numerical_count += 1

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
        "numerical_count": numerical_count,
        "concept_keys": concept_keys,
        "duplicate_concept_keys": duplicate_concept_keys,
        "flagged_count": flagged_count,
    }
