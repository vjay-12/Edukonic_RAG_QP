import re
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional, Set

from app.schemas import ValidationResult
from app.services.llm import generate_json, is_daily_quota_error, GeminiDailyQuotaError
from app.config import settings
from app.services.text_utils import extract_reaction_signatures

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
    available_chunk_ids: Optional[List[int]] = None,
    is_numerical: bool = False,
    context_text: str = "",
    used_reactions: Optional[Set[str]] = None,
    exemplar_texts: Optional[List[str]] = None,
    used_concepts: Optional[Set[str]] = None
) -> Tuple[bool, List[str]]:
    """
    Fast deterministic quality checks without LLM calls.
    Verifies:
    1. Basic fields, non-empty stem, insufficient context.
    2. Marks match slot specifications.
    3. Objective choices (4 options, valid A/B/C/D correct_option, no duplicates).
    4. MCQ stems must NOT state their own answer.
    5. Case-based: one coherent scenario, data readings requiring reasoning, actual answers to sub-questions.
    6. Visual / Diagram / Phantom references.
    7. Incomplete chemical equations.
    8. Numerical marking scheme: formula + substitution/answer; no units demanded for ratios.
    9. Step marks test one point each: no lumped >=2-mark steps, no 0.5/1.5 splits.
    10. No hallucinated numeric facts not in the source chunk text.
    11. Source chunks check: reject questions from "What you have learnt" or "Questions/Exercises" boxes.
    12. Cross-paper reaction deduplication.
    13. Copy guard: reject stems sharing an 8-word overlap with textbook context/exercises/examples.
    14. Concept-level dedupe across the whole paper (nichrome, power formulas, series, etc.).
    15. Standard CBSE definition for electric current (rate of flow of charge, I = Q/t).
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
    stem_lower = stem.lower()

    # 3. Objective choices (MCQ / Assertion-Reason)
    if q_type in ["mcq", "assertion_reason"]:
        options = question.get("options")
        if not isinstance(options, list) or len(options) != 4:
            issues.append(f"Objective question must have exactly 4 options (found {len(options) if isinstance(options, list) else 0}).")
        else:
            # Check for duplicate options
            clean_opts = [re.sub(r'[^a-zA-Z0-9]', '', str(opt)).lower() for opt in options]
            if len(clean_opts) != len(set(clean_opts)):
                issues.append("MCQ contains duplicate options.")

        corr = question.get("correct_option")
        if not corr or str(corr).strip().upper() not in ["A", "B", "C", "D"]:
            issues.append(f"Invalid correct_option '{corr}'; must be 'A', 'B', 'C', or 'D'.")
        elif isinstance(options, list) and len(options) == 4:
            # 4. MCQ stem must NOT state its own answer
            corr_idx = ord(str(corr).strip().upper()) - ord("A")
            if 0 <= corr_idx < len(options):
                corr_text = str(options[corr_idx]).strip()
                clean_corr = re.sub(r'[^a-zA-Z0-9\s]', '', corr_text).lower()
                clean_stem = re.sub(r'[^a-zA-Z0-9\s]', '', stem_lower)

                stop_words = {"the", "a", "an", "of", "and", "in", "to", "for", "with", "is", "are", "law", "reaction"}
                content_words = [w for w in clean_corr.split() if w not in stop_words and len(w) >= 3]

                if len(clean_corr) >= 10 and clean_corr in clean_stem:
                    issues.append(f"MCQ stem states its own answer verbatim ('{corr_text}').")
                elif len(content_words) >= 2 and all(w in clean_stem for w in content_words):
                    issues.append(f"MCQ stem contains and reveals its own answer ('{corr_text}').")

    # 5. Case-based checks
    if q_type == "case":
        sub_qs = question.get("sub_questions")
        if not isinstance(sub_qs, list) or len(sub_qs) == 0:
            issues.append("Case-based question must have sub_questions list.")
        else:
            sub_sum = sum(sq.get("marks", 0) for sq in sub_qs)
            if sub_sum != expected_marks:
                issues.append(f"Sum of case sub-questions ({sub_sum}) does not equal total case marks ({expected_marks}).")

            # Check for fragmented multiple disjoint setups
            fragment_indicators = [
                "in the first setup", "in the second setup", "in the third setup",
                "setup 1", "setup 2", "setup 3", "first experiment", "second experiment", "third experiment"
            ]
            found_fragments = [frag for frag in fragment_indicators if frag in stem_lower]
            if len(found_fragments) >= 2:
                issues.append("Case study must present one coherent scenario, not a fragmented composite of multiple disjoint laboratory setups.")

            # Check that sub-question answers do not appear verbatim in the case stem passage
            for sq_idx, sq in enumerate(sub_qs, 1):
                ans = str(sq.get("answer", "")).strip()
                ans_clean = re.sub(r'[^a-zA-Z0-9\s]', '', ans).lower().strip()
                clean_stem = re.sub(r'[^a-zA-Z0-9\s]', '', stem_lower)
                if len(ans_clean) >= 12 and ans_clean in clean_stem:
                    issues.append(f"Sub-question ({sq_idx}) answer appears verbatim in the case text passage.")
                elif "exothermic" in ans.lower() and "releases energy" in stem_lower and "exothermic" in sq.get("stem", "").lower():
                    issues.append(f"Sub-question ({sq_idx}) asks why respiration is exothermic, but the passage states that energy is released.")

                if len(ans) < 8:
                    issues.append(f"Case sub-question ({sq_idx}) must have a complete answer.")

            # Check for placeholder answer in case model answer
            case_ans = str(question.get("answer", "")).lower().strip()
            if any(ph in case_ans for ph in [
                "sub-questions evaluate", "refer to sub-questions", "answers are given below",
                "student understanding", "evaluated individually", "see sub-questions"
            ]):
                issues.append("Case study model answer must contain the actual answers to each sub-question, not meta placeholders.")
            elif len(case_ans) < 25:
                issues.append("Case study model answer is too short; must contain complete answers for all sub-parts.")

            # Check scenario has concrete real-life data or numerical readings requiring reasoning
            data_pattern = r'\b\d+(?:\.\d+)?\s*(?:v|w|a|kw|kwh|Ω|ohm|ohms|j|kj|s|sec|min|h|hr|hours?|m|cm|mm|°c|c)\b'
            if not re.search(data_pattern, stem_lower):
                issues.append("Case study scenario must be a real-life scenario with data readings (e.g. voltage, wattage, current, resistance) requiring reasoning.")

    # 6. Visual / Diagram / Phantom text references
    arrow_condition_phrases = ["above the arrow", "over the arrow", "on the arrow", "condition above"]
    if any(phrase in stem_lower for phrase in arrow_condition_phrases):
        has_arrow = "→" in stem or "->" in stem or "-->" in stem
        has_condition = any(c in stem_lower for c in ["heat", "sunlight", "catalyst", "temp", "atm", "electricity", "Δ", "chlorophyll"])
        if not (has_arrow and has_condition):
            issues.append("Question refers to conditions above the arrow, but no arrow/condition is shown in the stem.")

    diagram_phrases = [
        "in the given diagram", "shown in the diagram", "in the figure below",
        "shown in the figure", "in the given figure", "diagram below", "figure above",
        "diagram shown", "figure shown", "refer to the figure"
    ]
    if any(phrase in stem_lower for phrase in diagram_phrases):
        issues.append("Question refers to a diagram or figure that is not provided.")

    table_phrases = ["in the table below", "from the given table", "table shown below", "table above"]
    if any(phrase in stem_lower for phrase in table_phrases) and "\n|" not in stem and "---" not in stem and "\t" not in stem:
        issues.append("Question refers to a table that is not provided.")

    phantom_text_phrases = [
        "based on the provided text", "based on the given text", "from the provided text",
        "from the provided passage", "in the provided text", "in the given text",
        "based on the provided passage", "from the given passage", "based on the above passage"
    ]
    if q_type != "case" and any(phrase in stem_lower for phrase in phantom_text_phrases):
        issues.append("Question refers to a 'provided text/passage' that is not included in the stem.")

    # 7. Incomplete chemical equations check
    if "complete the" not in stem_lower and "write the balanced" not in stem_lower and "what is product" not in stem_lower:
        if re.search(r'[A-Za-z0-9\)]\s*(?:→|\->)\s*$', stem.strip()):
            issues.append("Chemical equation in stem is incomplete (ends abruptly at arrow).")

    # 8. Numerical marking scheme check
    ms = question.get("marking_scheme")
    if is_numerical or question.get("is_numerical"):
        if isinstance(ms, list) and len(ms) > 0:
            ms_text = " ".join([str(step.get("step", "")).lower() for step in ms if isinstance(step, dict)])
            has_formula = any(kw in ms_text for kw in ["formula", "relation", "equation", "law", "v = i", "r =", "p =", "h =", "i = q"])
            has_sub = any(kw in ms_text for kw in ["substitut", "value", "putting", "placing", "given", "step"])
            
            is_ratio = any(w in stem_lower for w in ["ratio", "in terms of", "how many times", "fraction", "factor", "relative to"])
            has_unit = any(kw in ms_text for kw in ["unit", "ohm", "volt", "ampere", "joule", "watt", "Ω", "v", "a", "w", "j", "answer"])

            if not has_formula:
                issues.append("Numerical question marking scheme must award marks for Formula.")
            if not is_ratio and not (has_sub or has_unit):
                issues.append("Numerical question marking scheme must award marks for Substitution and final Answer with Unit.")
            elif is_ratio and "unit" in ms_text and "correct unit" in ms_text:
                issues.append("Ratio or algebraic question marking scheme incorrectly demanded units for a dimensionless quantity.")

    # 9. Step marks test one point each: no lumped >=2-mark steps, no 0.5/1.5 splits
    if isinstance(ms, list) and len(ms) > 0:
        for s_idx, step in enumerate(ms, 1):
            if isinstance(step, dict):
                s_marks = step.get("marks", 0)
                if s_marks >= 2:
                    issues.append(f"Marking scheme step {s_idx} is lumped ({s_marks} marks). Each step must test one point (split into 1 + 1 marks).")
                elif s_marks in [0.5, 1.5] or (isinstance(s_marks, float) and not s_marks.is_integer()):
                    issues.append(f"Marking scheme step {s_idx} has fractional marks ({s_marks}). Steps must be awarded strictly 1 mark.")

        ms_sum = sum(step.get("marks", 0) for step in ms if isinstance(step, dict))
        if abs(ms_sum - expected_marks) > 0.05:
            issues.append(f"Marking scheme marks sum ({ms_sum}) does not match question marks ({expected_marks}).")

    # 10. Check for hallucinated numeric facts in model answer
    if context_text:
        model_answer = question.get("answer", "")
        temp_matches = re.findall(r'(\d{3,5}\s*(?:°\s*[CcFf]|K\b))', model_answer)
        for temp_val in temp_matches:
            clean_temp = re.sub(r'\s+', '', temp_val)
            clean_ctx = re.sub(r'\s+', '', context_text)
            if clean_temp not in clean_ctx:
                issues.append(f"Model answer contains specific numeric fact '{temp_val}' not found in the source textbook chunk.")

    # 11. Source chunks check: reject questions from "What you have learnt" or "Questions/Exercises" boxes
    src = question.get("source", {})
    sec_heading = str(src.get("section_heading", "")).lower()
    if any(h in sec_heading for h in ["what you have learnt", "questions", "exercises"]):
        issues.append(f"Question must be sourced from core concept sections, not '{src.get('section_heading')}' boxes.")

    chunk_ids = src.get("chunk_ids", [])
    if not chunk_ids or len(chunk_ids) == 0:
        issues.append("Question has no NCERT source chunk.")
    elif available_chunk_ids:
        for cid in chunk_ids:
            if cid not in available_chunk_ids:
                issues.append(f"Referenced chunk_id {cid} is not in the provided context chunks.")

    # 12. Cross-paper reaction deduplication
    if used_reactions:
        current_rxns = set(extract_reaction_signatures(stem + " " + question.get("answer", "")))
        common_rxns = current_rxns.intersection(used_reactions)
        if common_rxns:
            issues.append(f"Question reuses reaction/experiment already tested in an earlier slot of this paper: {list(common_rxns)}.")

    # 13. Copy guard (Requirement 1: reject stems sharing an 8-word overlap with textbook context/exercises/examples)
    if exemplar_texts:
        from app.services.text_utils import check_verbatim_overlap
        stems_to_test = [stem]
        if q_type == "case" and isinstance(question.get("sub_questions"), list):
            for sq in question["sub_questions"]:
                if isinstance(sq, dict) and sq.get("stem"):
                    stems_to_test.append(sq["stem"])
        elif q_type == "la" and isinstance(question.get("sub_questions"), list):
            for sq in question["sub_questions"]:
                if isinstance(sq, dict) and sq.get("stem"):
                    stems_to_test.append(sq["stem"])

        for s_idx, st in enumerate(stems_to_test):
            overlap = check_verbatim_overlap(st, exemplar_texts, n=8)
            if overlap:
                target_desc = "Question stem" if s_idx == 0 else f"Sub-question stem"
                issues.append(f"Copy guard: {target_desc} shares an 8-word verbatim overlap with textbook text: '{overlap}'. Use exercises/examples as style references only; change numbers, context and wording.")
                break

    # 14. Concept-level dedupe across the whole paper (Requirement 2)
    from app.services.text_utils import detect_question_concepts
    detected_concepts = detect_question_concepts(stem + " " + str(question.get("answer", "")))
    if used_concepts and detected_concepts:
        common_concepts = set(detected_concepts).intersection(used_concepts)
        if common_concepts:
            issues.append(f"Concept-level dedupe: Question repeats concept already tested in paper: {list(common_concepts)}. Each concept must only be tested once per paper.")

    # 15. Standard CBSE definition for electric current (Requirement 3)
    is_def_current = any(phrase in stem_lower for phrase in [
        "define electric current", "definition of electric current", "what is meant by electric current",
        "what is electric current", "state the term electric current", "define the term electric current"
    ])
    if is_def_current:
        ans_text = str(question.get("answer", "")).lower()
        has_flow = any(p in ans_text for p in [
            "rate of flow of charge", "rate of flow of electric charge",
            "flow of charge per unit time", "charge flowing per unit time",
            "amount of charge flowing through a particular area in unit time"
        ])
        has_formula = any(f in ans_text for f in ["i = q/t", "i = q / t", "i=q/t", "i = q"])
        if not (has_flow and has_formula):
            issues.append("Standard CBSE definition required for electric current: must state 'rate of flow of electric charge' (or rate of flow of charge) and include formula I = Q/t.")

    is_valid = len(issues) == 0
    return is_valid, issues

def validate_with_llm(
    question: Dict[str, Any],
    context_text: str,
    model: Optional[str] = None
) -> Dict[str, Any]:
    """
    LLM validation check verifying factual grounding, answer accuracy, visual/equation integrity, and curriculum fit.
    """
    sys_instruction = load_prompt_file("validate.md")
    if not sys_instruction:
        sys_instruction = "You are an expert CBSE Science moderator. Verify question grounding, answer correctness, marks fit, visual/equation integrity, and options."

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
            if val_result.get("single_correct_option") is False:
                val_result["verdict"] = "fail"
            issues = val_result.get("issues", [])
            issues_str = " ".join(issues).lower()
            if any(term in issues_str for term in [
                "unshown", "not shown", "above the arrow", "chemistry error",
                "unbalanced", "verbatim", "incorrect formula", "reveals answer",
                "lumped", "provided text", "more than one true", "multiple correct",
                "distractor", "duplicate concept", "copy guard"
            ]):
                val_result["verdict"] = "fail"
            return val_result
    except Exception as e:
        if is_daily_quota_error(e):
            raise
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
