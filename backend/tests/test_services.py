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

def test_copy_guard_and_concept_dedupe():
    from app.services.text_utils import check_verbatim_overlap, format_science_text, detect_question_concepts

    # 1. 8-gram copy guard
    exemplar = "An electric heater of resistance 44 Ω draws 5 A from the service mains for 2 hours. Calculate the rate at which heat is developed in the heater."
    copied_stem = "Calculate the rate at which heat is developed in the heater."
    overlap = check_verbatim_overlap(copied_stem, [exemplar], n=8)
    assert overlap is not None

    clean_stem = "A domestic immersion rod of resistance 25 Ω is connected to a 220 V line for 45 minutes."
    assert check_verbatim_overlap(clean_stem, [exemplar], n=8) is None

    # 2. Concept dedupe validation
    q1 = {
        "stem": "Why are coils of electric toasters made of nichrome alloy rather than pure metal?",
        "type": "vsa",
        "marks": 2,
        "answer": "Nichrome is an alloy with higher resistivity and does not oxidize easily.",
        "marking_scheme": [{"step": "Higher resistivity", "marks": 1}, {"step": "Resists oxidation", "marks": 1}],
        "source": {"chunk_ids": [598], "section_heading": "11.7.1 Practical Applications"}
    }
    concepts_q1 = detect_question_concepts(q1["stem"] + " " + q1["answer"])
    assert "nichrome_alloy" in concepts_q1

    # Deterministic check with used_concepts
    is_ok, issues = validate_deterministic(q1, expected_marks=2, expected_type="vsa", available_chunk_ids=[598], used_concepts={"nichrome_alloy"})
    assert is_ok is False
    assert any("repeats concept already tested" in i for i in issues)

def test_cbse_current_definition_and_case_validation():
    # 1. Non-CBSE current definition
    bad_current_q = {
        "stem": "Define electric current and state its unit.",
        "type": "vsa",
        "marks": 2,
        "answer": "Electric current is the movement of electrons through a wire. Unit is ampere.",
        "marking_scheme": [{"step": "Definition", "marks": 1}, {"step": "Unit", "marks": 1}],
        "source": {"chunk_ids": [561], "section_heading": "11.1 Electric Current"}
    }
    is_ok, issues = validate_deterministic(bad_current_q, expected_marks=2, expected_type="vsa", available_chunk_ids=[561])
    assert is_ok is False
    assert any("Standard CBSE definition required for electric current" in i for i in issues)

    # Valid CBSE current definition
    good_current_q = {
        "stem": "Define electric current and state its SI unit.",
        "type": "vsa",
        "marks": 2,
        "answer": "Electric current is expressed as the rate of flow of electric charges. Mathematically, I = Q/t. The SI unit is ampere (A).",
        "marking_scheme": [{"step": "Rate of flow of electric charge and formula I = Q/t", "marks": 1}, {"step": "SI unit is ampere", "marks": 1}],
        "source": {"chunk_ids": [561], "section_heading": "11.1 Electric Current"}
    }
    is_ok, issues = validate_deterministic(good_current_q, expected_marks=2, expected_type="vsa", available_chunk_ids=[561])
    assert is_ok is True

    # 2. Case study validation (placeholder answer and missing data)
    bad_case = {
        "stem": "A circuit was built by students in a physics lab. Based on the above information, answer the following questions:",
        "type": "case",
        "marks": 4,
        "sub_questions": [
            {"stem": "Find the total current.", "marks": 1, "answer": "I = 2 A"},
            {"stem": "Find the potential difference.", "marks": 1, "answer": "V = 10 V"},
            {"stem": "Explain the relationship.", "marks": 2, "answer": "Ohm's law states V is proportional to I."}
        ],
        "answer": "Sub-questions evaluate student understanding.",
        "marking_scheme": [{"step": "Step 1", "marks": 1}, {"step": "Step 2", "marks": 1}, {"step": "Step 3", "marks": 1}, {"step": "Step 4", "marks": 1}],
        "source": {"chunk_ids": [586], "section_heading": "11.6.2 Resistors in Parallel"}
    }
    is_ok, issues = validate_deterministic(bad_case, expected_marks=4, expected_type="case", available_chunk_ids=[586])
    assert is_ok is False
    assert any("placeholder" in i for i in issues)
    assert any("real-life scenario with data readings" in i for i in issues)

def test_science_formatting_rules():
    from app.services.text_utils import format_science_text

    raw = "Formula P = I^2R = V^2/R and area is pi * d^2 / 4. Resistance is 44 ̇Ω and 26 \u2126 and 10 ohms."
    formatted = format_science_text(raw)
    assert "I²R" in formatted
    assert "V²/R" in formatted
    assert "π" in formatted
    assert "d²" in formatted
    assert " × " in formatted
    assert "44 Ω" in formatted
    assert "26 Ω" in formatted
    assert "10 Ω" in formatted


def test_llm_usage_tracker_and_stats():
    from app.services.llm import (
        reset_llm_stats,
        get_llm_stats,
        get_llm_usage_summary,
        get_llm_tracker,
    )

    reset_llm_stats()
    tracker = get_llm_tracker()

    stats = get_llm_stats()
    assert stats["calls"] == 0
    assert stats["total_tokens"] == 0
    assert stats["cache_hits"] == 0

    tracker.record_call(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    tracker.record_call(prompt_tokens=200, completion_tokens=80, total_tokens=280)
    tracker.record_cache_hit()

    stats = get_llm_stats()
    assert stats["calls"] == 2
    assert stats["prompt_tokens"] == 300
    assert stats["completion_tokens"] == 130
    assert stats["total_tokens"] == 430
    assert stats["cache_hits"] == 1

    summary = get_llm_usage_summary()
    assert "2 calls" in summary
    assert "1 cache hits" in summary
    assert "430 total tokens" in summary


def test_daily_quota_error_detection_and_non_retry():
    from app.services.llm import (
        is_daily_quota_error,
        is_retryable_llm_error,
        GeminiDailyQuotaError,
        DAILY_QUOTA_ERROR_MESSAGE,
    )

    # 1. Daily quota exceptions
    daily_msg_1 = "ResourceExhausted: 429 Quota exceeded for quota metric 'Generate Content API requests per day' and limit '...PerDay...'"
    daily_msg_2 = "429 RESOURCE_EXHAUSTED. Quota exceeded for quota metric 'GenerateContentRequestsPerDayPerProjectPerRegion'"
    daily_msg_3 = "429 Too Many Requests: daily quota exhausted"

    assert is_daily_quota_error(RuntimeError(daily_msg_1)) is True
    assert is_daily_quota_error(RuntimeError(daily_msg_2)) is True
    assert is_daily_quota_error(RuntimeError(daily_msg_3)) is True
    assert is_daily_quota_error(GeminiDailyQuotaError()) is True

    # Daily quota errors MUST NOT be retryable
    assert is_retryable_llm_error(RuntimeError(daily_msg_1)) is False
    assert is_retryable_llm_error(GeminiDailyQuotaError()) is False

    # 2. Transient per-minute rate limit (RPM/TPM) MUST be retryable
    per_minute_msg = "429 RESOURCE_EXHAUSTED. Quota exceeded for quota metric 'Generate Content API requests per minute' and limit '...PerMinute...'"
    assert is_daily_quota_error(RuntimeError(per_minute_msg)) is False
    assert is_retryable_llm_error(RuntimeError(per_minute_msg)) is True

    transient_503 = "503 UNAVAILABLE. The model is currently experiencing high demand."
    assert is_daily_quota_error(RuntimeError(transient_503)) is False
    assert is_retryable_llm_error(RuntimeError(transient_503)) is True

    # Error message check
    err = GeminiDailyQuotaError()
    assert str(err) == DAILY_QUOTA_ERROR_MESSAGE
    assert str(err) == "Daily Gemini quota reached, resets around 12:30 PM IST"


def test_llm_cache_identical_prompts(tmp_path):
    from app.services.llm import LLMCache
    import json

    db_file = tmp_path / "test_cache.db"
    cache = LLMCache(db_path=db_file)

    cache_key = "test_cache_key_123"
    payload = {"stem": "What is resistance?", "answer": "Opposition to current"}

    assert cache.get(cache_key) is None

    cache.set(cache_key, json.dumps(payload), model="test-model", prompt_tokens=50, completion_tokens=20)
    cached_val = cache.get(cache_key)
    assert cached_val is not None
    assert json.loads(cached_val) == payload

    # Re-reading from SQLite directly
    cache_2 = LLMCache(db_path=db_file)
    assert json.loads(cache_2.get(cache_key)) == payload


def test_configurable_generator_and_validator_models():
    from app.config import settings

    # Both models must be configurable
    assert hasattr(settings, "GEN_MODEL")
    assert hasattr(settings, "VALIDATE_MODEL")
    assert settings.GEN_MODEL is not None
    assert settings.VALIDATE_MODEL is not None


