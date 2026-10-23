import pytest
from app.schemas import PaperConfig, ChapterWeight, SectionConfig
from app.services.planner import allocate_counts_largest_remainder, plan_paper_slots, compute_blueprint_report
from app.services.validator import validate_deterministic
from app.services.dedupe import cosine_similarity, check_duplicate
from app.services.exporter import export_paper_docx, export_answer_key_docx

def test_largest_remainder_allocation():
    weights = {"A": 0.4, "B": 0.3, "C": 0.3}
    res = allocate_counts_largest_remainder(10, weights)
    assert sum(res.values()) == 10
    assert res["A"] == 4
    assert res["B"] == 3
    assert res["C"] == 3

    # Odd numbers with remainders
    res2 = allocate_counts_largest_remainder(11, weights)
    assert sum(res2.values()) == 11

def test_plan_paper_slots():
    cfg = PaperConfig(
        title="Test Blueprint",
        class_num=10,
        subject="Science",
        total_marks=25,
        chapters=[
            ChapterWeight(chapter_no=1, weight=0.4),
            ChapterWeight(chapter_no=5, weight=0.3),
            ChapterWeight(chapter_no=11, weight=0.3),
        ],
        sections=[
            SectionConfig(id="A", type="mcq", count=6, marks=1),
            SectionConfig(id="B", type="vsa", count=2, marks=2),
            SectionConfig(id="C", type="sa", count=2, marks=3),
            SectionConfig(id="D", type="la", count=1, marks=5),
            SectionConfig(id="E", type="case", count=1, marks=4),
        ],
        difficulty_mix={"easy": 0.3, "medium": 0.5, "hard": 0.2},
        competency_percent=40,
    )

    slots = plan_paper_slots(cfg)
    assert len(slots) == 12
    # Verify slot numbers are sequential
    assert [s["slot_no"] for s in slots] == list(range(1, 13))

    # Verify total marks across slots
    total_marks = sum(s["marks"] for s in slots)
    assert total_marks == 25

    # Check chapters allocated
    ch_assigned = [s["chapter_no"] for s in slots]
    assert 1 in ch_assigned
    assert 5 in ch_assigned
    assert 11 in ch_assigned

    # Check case is competency
    case_slots = [s for s in slots if s["type"] == "case"]
    assert len(case_slots) == 1
    assert case_slots[0]["competency"] is True

def test_validate_deterministic_pass_and_fail():
    # Valid MCQ
    valid_mcq = {
        "stem": "What is the SI unit of electric potential difference?",
        "type": "mcq",
        "marks": 1,
        "options": ["Ampere", "Volt", "Ohm", "Watt"],
        "correct_option": "B",
        "source": {"chunk_ids": [101], "pages": [3]},
        "marking_scheme": [{"step": "Correct option B", "marks": 1.0}],
    }
    is_ok, issues = validate_deterministic(valid_mcq, expected_marks=1, expected_type="mcq", available_chunk_ids=[101])
    assert is_ok is True
    assert len(issues) == 0

    # Invalid MCQ - only 3 options and wrong correct_option
    bad_mcq = {
        "stem": "What is electric current?",
        "type": "mcq",
        "marks": 1,
        "options": ["Option 1", "Option 2", "Option 3"],
        "correct_option": "Z",
        "source": {"chunk_ids": [101]},
    }
    is_ok, issues = validate_deterministic(bad_mcq, expected_marks=1, expected_type="mcq", available_chunk_ids=[101])
    assert is_ok is False
    assert any("exactly 4 options" in i for i in issues)
    assert any("Invalid correct_option" in i for i in issues)

    # Invalid Case question - sub-question marks mismatch
    bad_case = {
        "stem": "Read passage...",
        "type": "case",
        "marks": 4,
        "sub_questions": [
            {"stem": "Part 1", "marks": 1},
            {"stem": "Part 2", "marks": 1},
        ], # Sum is 2, expected 4
        "source": {"chunk_ids": [101]},
    }
    is_ok, issues = validate_deterministic(bad_case, expected_marks=4, expected_type="case", available_chunk_ids=[101])
    assert is_ok is False
    assert any("Sum of case sub-questions" in i for i in issues)

def test_dedupe_cosine_similarity():
    v1 = [1.0, 0.0, 0.0]
    v2 = [1.0, 0.0, 0.0]
    v3 = [0.0, 1.0, 0.0]

    assert abs(cosine_similarity(v1, v2) - 1.0) < 1e-4
    assert abs(cosine_similarity(v1, v3) - 0.0) < 1e-4

    is_dup, max_sim = check_duplicate(v1, [v3], threshold=0.80)
    assert is_dup is False

    is_dup, max_sim = check_duplicate(v1, [v2], threshold=0.80)
    assert is_dup is True
    assert max_sim >= 0.99

def test_docx_export_generation():
    paper_dict = {
        "title": "Unit Test 1",
        "config": {
            "class": 10,
            "subject": "Science",
            "total_marks": 5,
            "header": {
                "school_name": "Test Public School",
                "exam_name": "Mid-Term Exam",
                "duration": "1 Hour",
                "instructions": ["All questions compulsory."],
            },
        },
    }
    questions = [
        {
            "id": 1,
            "slot_no": 1,
            "section": "A",
            "type": "mcq",
            "marks": 1,
            "chapter_no": 11,
            "content": {
                "stem": "What is the SI unit of resistance?",
                "options": ["Ohm", "Volt", "Ampere", "Joule"],
                "correct_option": "A",
                "answer": "Ohm (Ω) is the SI unit of electrical resistance.",
                "marking_scheme": [{"step": "Option A (Ohm)", "marks": 1.0}],
                "source": {"pages": [10, 11]},
            },
        }
    ]

    # Test Paper DOCX
    stream_paper = export_paper_docx(paper_dict, questions)
    assert stream_paper.getvalue()[:4] == b"PK\x03\x04"

    # Test Key DOCX
    stream_key = export_answer_key_docx(paper_dict, questions)
    assert stream_key.getvalue()[:4] == b"PK\x03\x04"
