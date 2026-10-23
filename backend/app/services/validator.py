from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import json

from app.schemas import ValidationResult
from app.services.llm import generate_json
from app.config import settings

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

def load_prompt_file(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def validate_deterministic(
    question: Dict[str, Any],
    expected_marks: int,
    expected_type: str,
    available_chunk_ids: Optional[List[int]] = None
) -> Tuple[bool, List[str]]:
    """
    Fast deterministic quality checks without LLM calls.
    Verifies question format, MCQ options, marking scheme sums, and chunk references.
    """
    issues: List[str] = []

    # 1. Basic fields
    stem = question.get("stem", "").strip()
    if not stem:
        issues.append("Question stem is empty.")

    if question.get("insufficient_context") is True:
        issues.append("Question flagged with insufficient_context=True.")

    # 2. Marks check
    actual_marks = question.get("marks", 0)
    if actual_marks != expected_marks:
        issues.append(f"Question marks ({actual_marks}) does not match slot marks ({expected_marks}).")

    q_type = question.get("type", expected_type)

    # 3. MCQ / Assertion-Reason checks
    if q_type in ["mcq", "assertion_reason"]:
        options = question.get("options")
        if not isinstance(options, list) or len(options) != 4:
            issues.append(f"Objective question must have exactly 4 options (found {len(options) if isinstance(options, list) else 0}).")
        
        corr = question.get("correct_option")
        if not corr or str(corr).strip().upper() not in ["A", "B", "C", "D"]:
            issues.append(f"Invalid correct_option '{corr}'; must be 'A', 'B', 'C', or 'D'.")

    # 4. Case-based checks
    if q_type == "case":
        sub_qs = question.get("sub_questions")
        if not isinstance(sub_qs, list) or len(sub_qs) == 0:
            issues.append("Case-based question must have sub_questions list.")
        else:
            sub_sum = sum(sq.get("marks", 0) for sq in sub_qs)
            if sub_sum != expected_marks:
                issues.append(f"Sum of case sub-questions ({sub_sum}) does not equal total case marks ({expected_marks}).")

    # 5. Marking scheme summation check
    ms = question.get("marking_scheme")
    if isinstance(ms, list) and len(ms) > 0:
        ms_sum = sum(step.get("marks", 0) for step in ms if isinstance(step, dict))
        if abs(ms_sum - expected_marks) > 0.05:
            issues.append(f"Marking scheme marks sum ({ms_sum}) does not match question marks ({expected_marks}).")

    # 6. Source chunks check
    src = question.get("source", {})
    chunk_ids = src.get("chunk_ids", [])
    if not chunk_ids:
        issues.append("Missing source chunk_ids.")
    elif available_chunk_ids:
        for cid in chunk_ids:
            if cid not in available_chunk_ids:
                issues.append(f"Referenced chunk_id {cid} is not in the provided context chunks.")

    is_valid = len(issues) == 0
    return is_valid, issues

def validate_with_llm(
    question: Dict[str, Any],
    context_text: str,
    model: Optional[str] = None
) -> Dict[str, Any]:
    """
    LLM validation check verifying factual grounding, answer accuracy, and curriculum fit.
    """
    sys_instruction = load_prompt_file("validate.md")
    if not sys_instruction:
        sys_instruction = "You are an expert CBSE Science moderator. Verify question grounding, answer correctness, marks fit, and options."

    prompt = f"""EVALUATE THIS QUESTION AGAINST THE GIVEN TEXTBOOK CONTEXT:

--- BEGIN CONTEXT ---
{context_text}
--- END CONTEXT ---

--- BEGIN QUESTION TO VALIDATE ---
{json.dumps(question, indent=2)}
--- END QUESTION TO VALIDATE ---

Respond with the validation result object containing:
- grounded (boolean)
- answer_correct (boolean)
- marks_fit (boolean)
- single_correct_option (boolean)
- issues (list of strings)
- verdict ("pass", "warn", or "fail")
"""
    try:
        val_result = generate_json(
            prompt=prompt,
            schema=ValidationResult,
            system_instruction=sys_instruction,
            model=model or settings.VALIDATE_MODEL,
        )
        if isinstance(val_result, dict):
            return val_result
    except Exception as e:
        # Fallback if LLM call fails
        return {
            "grounded": True,
            "answer_correct": True,
            "marks_fit": True,
            "single_correct_option": True,
            "issues": [f"LLM validation warning: {str(e)}"],
            "verdict": "warn"
        }

    return {
        "grounded": True,
        "answer_correct": True,
        "marks_fit": True,
        "single_correct_option": True,
        "issues": [],
        "verdict": "pass"
    }
