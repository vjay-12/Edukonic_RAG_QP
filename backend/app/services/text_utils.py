import re
from typing import List, Dict, Any, Optional

# Chemical element symbols commonly appearing in secondary school science curricula
ELEMENTS_REGEX = (
    r'(?:H|He|Li|Be|B|C|N|O|F|Ne|Na|Mg|Al|Si|P|S|Cl|Ar|K|Ca|Cr|Mn|Fe|Co|Ni|Cu|Zn|Br|Ag|Sn|I|Ba|Pt|Au|Hg|Pb|\))'
)

SUB_MAP = str.maketrans('0123456789', '₀₁₂₃₄₅₆₇₈₉')
ROMAN_NUMERALS = ["(i)", "(ii)", "(iii)", "(iv)", "(v)", "(vi)", "(vii)", "(viii)"]

KNOWN_REACTIONS = [
    {
        "id": "copper_oxidation",
        "primary": ["copper", "cuo"],
        "indicators": ["copper powder", "copper(ii) oxide", "copper (ii) oxide", "black copper", "cuo", "heating copper", "heated copper", "black coating on copper"],
        "excludes": ["coating formed on silver", "black coating is formed on silver", "coating formed on copper when it corrodes", "coating on copper when it corrodes"],
    },
    {
        "id": "zinc_acid_reaction",
        "primary": ["zinc", "zn"],
        "indicators": ["zinc granules", "dilute sulphuric", "dilute sulfuric", "dilute hydrochloric", "zinc sulphate", "zinc sulfate", "znso4", "zn + h2so4", "zn + hcl"],
        "excludes": [],
    },
    {
        "id": "barium_precipitation",
        "primary": ["barium", "baso4"],
        "indicators": ["barium chloride", "sodium sulphate", "sodium sulfate", "aluminium sulphate", "barium sulphate", "barium sulfate", "white precipitate of barium", "bacl2", "baso4"],
        "excludes": [],
    },
    {
        "id": "lead_nitrate_decomposition",
        "primary": ["lead nitrate", "pb(no3)2", "lead(ii) nitrate"],
        "indicators": ["brown fumes", "nitrogen dioxide", "lead oxide", "pbo", "decomposition of lead nitrate"],
        "excludes": [],
    },
    {
        "id": "ferrous_sulphate_decomposition",
        "primary": ["ferrous sulphate", "ferrous sulfate", "feso4"],
        "indicators": ["green crystals", "ferric oxide", "fe2o3", "sulphur dioxide", "burning sulphur", "decomposition of ferrous"],
        "excludes": [],
    },
    {
        "id": "calcium_reactions",
        "primary": ["calcium", "cao", "ca(oh)2", "caco3"],
        "indicators": ["quicklime", "slaked lime", "limestone", "whitewashing", "calcium hydroxide", "calcium oxide"],
        "excludes": [],
    },
    {
        "id": "water_electrolysis",
        "primary": ["electrolysis"],
        "indicators": ["electrolysis of water", "acidified water", "volume of hydrogen", "ratio of hydrogen", "carbon electrodes", "test tubes over electrodes"],
        "excludes": [],
    },
    {
        "id": "silver_photolysis",
        "primary": ["silver chloride", "silver bromide", "agcl", "agbr"],
        "indicators": ["sunlight", "photochemical", "photolysis", "turns grey in sunlight", "black and white photography"],
        "excludes": [],
    },
    {
        "id": "magnesium_burning",
        "primary": ["magnesium", "mg"],
        "indicators": ["magnesium ribbon", "dazzling white flame", "magnesium oxide", "mgo", "cleaning with sandpaper"],
        "excludes": [],
    },
    {
        "id": "iron_steam_reaction",
        "primary": ["iron", "steam", "fe3o4"],
        "indicators": ["iron and steam", "iron with steam", "iron plus water", "fe + h2o", "fe3o4"],
        "excludes": ["rusting of iron", "corrosion of iron"],
    },
    {
        "id": "corrosion_rancidity",
        "primary": ["corrosion", "rusting", "rancidity", "rancid"],
        "indicators": ["rusting of iron", "coating on silver", "coating on copper", "green coating", "black coating on silver", "antioxidants", "flushed with nitrogen", "rancid smell"],
        "excludes": [],
    },
    {
        "id": "respiration_exothermic",
        "primary": ["respiration"],
        "indicators": ["glucose combines with oxygen", "c6h12o6", "exothermic process", "energy released during respiration"],
        "excludes": [],
    },
]

def format_marks(marks: Any) -> str:
    """Format marks strictly as '1 mark' or 'N marks', avoiding floating point '1.0 Mark'."""
    try:
        val = float(marks)
        val_int = int(val) if val == int(val) else val
        return f"{val_int} mark" if val_int == 1 else f"{val_int} marks"
    except (ValueError, TypeError):
        return f"{marks} marks"

SUB_MAP_SUPER = str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹')

def format_chemical_formulas(text: str) -> str:
    """
    Format chemical formulas with proper Unicode subscripts and arrows.
    Examples:
        H2SO4 -> H₂SO₄
        Ca(OH)2 -> Ca(OH)₂
        2Pb(NO3)2 -> 2Pb(NO₃)₂
        A + B -> C + D -> A + B → C + D
    """
    if not text:
        return ""

    # Replace arrow notations
    formatted = re.sub(r'—\s*\(([^\)]+)\)\s*→', r' → (\1) ', text)
    formatted = re.sub(r'\-\s*\(([^\)]+)\)\s*\->', r' → (\1) ', formatted)
    formatted = re.sub(r'\-\s*\[([^\]]+)\]\s*\->', r' → [\1] ', formatted)
    formatted = re.sub(r'(\-\->|\->|==>)', ' → ', formatted)
    formatted = re.sub(r'(<=>|<-->)', ' ⇌ ', formatted)

    # Convert numbers following chemical elements or closing parentheses to subscripts
    def replace_subscript(match: re.Match) -> str:
        elem = match.group(1)
        num = match.group(2)
        return elem + num.translate(SUB_MAP)

    chem_pattern = re.compile(rf'({ELEMENTS_REGEX})(\d+)')
    formatted = chem_pattern.sub(replace_subscript, formatted)

    # Clean double spaces around arrows
    formatted = re.sub(r' +→ +', ' → ', formatted)
    formatted = re.sub(r' +⇌ +', ' ⇌ ', formatted)

    return formatted

def format_science_text(text: str) -> str:
    """
    Format science, physics and math expressions:
    - Chemical formulas (H2SO4 -> H₂SO₄, arrows -> →)
    - pi -> π
    - d^2 -> d², d^3 -> d³, r^2 -> r², s^2 -> s², m^2 -> m²
    - I^2R -> I²R, V^2/R -> V²/R
    - Multiplication * -> ×
    - Normalize NCERT ohm symbols: drop combining dots '44 ̇Ω', normalize \u2126, \bohms?\b -> 'Ω'
    """
    if not text:
        return ""

    # 1. Chemical formulas first
    text = format_chemical_formulas(text)

    # 2. Normalize ohm symbols and OCR artifacts
    text = re.sub(r'[\u0307\u0323]\s*Ω', 'Ω', text)
    text = re.sub(r'[\u2126]', 'Ω', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*(?:ohms?|Ohms?)\b', r'\1 Ω', text)
    text = re.sub(r'(\d+(?:\.\d+)?)\s*Ω', r'\1 Ω', text)

    # 3. pi -> π
    text = re.sub(r'\bpi\b', 'π', text)

    # 4. Powers and formulas: d^2 -> d², I^2R -> I²R, V^2/R -> V²/R
    text = re.sub(r'\bI\^2\s*R\b', 'I²R', text)
    text = re.sub(r'\bV\^2\s*/\s*R\b', 'V²/R', text)
    text = re.sub(r'([a-zA-Z\)])\^([0-9]+)', lambda m: m.group(1) + m.group(2).translate(SUB_MAP_SUPER), text)

    # 5. Multiplication * -> ×
    text = re.sub(r'(?<=[a-zA-Z0-9\)²³⁴⁵⁶⁷⁸⁹⁰π])\s*\*\s*(?=[a-zA-Z0-9\(π])', ' × ', text)

    return text

def tokenize_words(text: str) -> List[str]:
    """Tokenize words for n-gram copy guard."""
    if not text:
        return []
    return [w.lower() for w in re.findall(r'[a-zA-Z0-9]+', text)]

def check_verbatim_overlap(stem: str, target_texts: List[str], n: int = 8) -> Optional[str]:
    """
    Copy guard: Check if stem shares an n-word verbatim overlap with any target textbook text.
    Returns the overlapping phrase if found, or None.
    """
    s_tokens = tokenize_words(stem)
    if len(s_tokens) < n:
        return None

    stem_ngrams = set(tuple(s_tokens[i:i+n]) for i in range(len(s_tokens) - n + 1))

    for target in target_texts:
        if not target:
            continue
        t_tokens = tokenize_words(target)
        if len(t_tokens) < n:
            continue
        for i in range(len(t_tokens) - n + 1):
            ng = tuple(t_tokens[i:i+n])
            if ng in stem_ngrams:
                return " ".join(ng)

    return None

def detect_question_concepts(text: str) -> List[str]:
    """
    Detect core scientific concepts tested in a question to enforce cross-paper deduplication:
    - nichrome_alloy
    - power_formulas
    - series_circuits
    - parallel_circuits
    - joules_heating
    - current_charge
    - potential_difference
    - ohms_law
    - factors_resistivity
    - heating_applications
    """
    if not text:
        return []
    t = text.lower()
    concepts = []

    # 1. Nichrome alloy / heating element
    if any(k in t for k in ["heating element", "heating elements", "coils of electric", "alloy rather than pure metal", "alloys do not oxidise", "nichrome alloy"]) or ("nichrome" in t and any(w in t for w in ["alloy", "toaster", "iron", "heater", "resistivity", "oxidise", "pure metal"])):
        concepts.append("nichrome_alloy")

    # 2. Electric Power & Energy formulas
    if any(k in t for k in [
        "electric power", "p = vi", "p = v·i", "p = i²r", "p = v²/r", "p = i^2r", "p = v^2/r",
        "rate at which electric energy is consumed", "commercial unit of electrical energy",
        "kwh", "kilowatt-hour", "rate at which heat is developed in the heater", "energy consumed by"
    ]):
        concepts.append("power_formulas")

    # 3. Resistors in Series
    if any(k in t for k in ["resistors in series", "series circuit", "series combination", "connected in series", "resistors are in series", "series arrangement"]):
        concepts.append("series_circuits")

    # 4. Resistors in Parallel
    if any(k in t for k in ["resistors in parallel", "parallel circuit", "parallel combination", "connected in parallel", "parallel network", "parallel arrangement"]):
        concepts.append("parallel_circuits")

    # 5. Joule's law of heating
    if any(k in t for k in ["joule's law", "joule s law", "h = i²rt", "h = i^2rt", "heat produced in a resistor", "heating effect of electric"]):
        concepts.append("joules_heating")

    # 6. Current and charge definition
    if any(k in t for k in ["rate of flow of electric charge", "rate of flow of charge", "i = q/t", "i = q / t", "define electric current", "definition of electric current", "constitutes an electric current"]):
        concepts.append("current_charge")

    # 7. Potential difference definition and work done
    if any(k in t for k in [
        "define electric potential", "definition of electric potential",
        "define 1 volt", "definition of 1 v", "definition of 1 volt",
        "define potential difference", "v = w/q", "w = v * q", "work done per unit charge",
        "work done in moving a unit charge", "difference of electric pressure", "1 joule per coulomb"
    ]):
        concepts.append("potential_difference")

    # 8. Ohm's law
    if any(k in t for k in ["ohm's law", "ohm s law", "v ∝ i", "v = ir", "v-i graph", "v-i relationship", "nature and geometrical property of the resulting plot"]):
        concepts.append("ohms_law")

    # 9. Factors affecting resistance & resistivity
    if any(k in t for k in ["resistivity", "r = ρl/a", "factors on which the resistance", "cross-section of wire", "area of cross-section", "doubled on itself"]):
        concepts.append("factors_resistivity")

    # 10. Heating applications (fuse / tungsten)
    if any(k in t for k in ["electric fuse", "fuse wire", "fuse rating", "tungsten filament", "filament of an electric bulb"]):
        concepts.append("heating_applications")

    return concepts

def strip_option_prefix(opt_text: str) -> str:
    """Strip duplicate option prefixes like 'A)', 'B)', '(A)', 'A.', 'Option A:' from option strings."""
    if not opt_text:
        return ""
    cleaned = str(opt_text).strip()
    cleaned = re.sub(r'^(?:\(?\s*[A-Da-d]\s*[\)\.\:\-]\s*|\bOption\s+\(?[A-Da-d]\)?[\:\.\-]?\s*)', '', cleaned)
    return cleaned.strip()

def strip_sub_question_prefix(stem_text: str) -> str:
    """Strip duplicate numbering prefix from sub-question stems (e.g. '(i)', '1.', '(a)')."""
    if not stem_text:
        return ""
    cleaned = str(stem_text).strip()
    cleaned = re.sub(r'^(?:\([iIvVaAbBcCdD0-9]+\)|[iIvVaAbBcCdD0-9]+[\.\)])\s*', '', cleaned)
    return cleaned.strip()

def get_roman_numeral(index: int) -> str:
    """Return 0-indexed roman numeral (0 -> (i), 1 -> (ii), etc.)."""
    if 0 <= index < len(ROMAN_NUMERALS):
        return ROMAN_NUMERALS[index]
    return f"({index + 1})"

def extract_reaction_signatures(text: str) -> List[str]:
    """Detect which known chemical reactions or key experiments are present in the text."""
    if not text:
        return []
    text_lower = text.lower()
    # Normalize unicode subscripts for matching (e.g. Fe₃O₄ -> fe3o4, BaSO₄ -> baso4)
    for sub, digit in [('₀', '0'), ('₁', '1'), ('₂', '2'), ('₃', '3'), ('₄', '4'), ('₅', '5'), ('₆', '6'), ('₇', '7'), ('₈', '8'), ('₉', '9')]:
        text_lower = text_lower.replace(sub, digit)

    signatures = []
    for rxn in KNOWN_REACTIONS:
        rxn_id = rxn["id"]
        # Check exclusion first
        if any(exc in text_lower for exc in rxn.get("excludes", [])):
            continue

        # Check primary trigger: at least one primary term must be present
        has_primary = any(p in text_lower for p in rxn["primary"])
        if not has_primary:
            continue

        # Check indicator: at least one indicator must match
        has_indicator = any(ind in text_lower for ind in rxn["indicators"])
        if has_indicator:
            signatures.append(rxn_id)

    return signatures

def build_canonical_citation(
    chapter_no: int,
    chapter_title: str,
    section_heading: Optional[str],
    page_start: int,
    page_end: int,
    chunk_id: int
) -> str:
    """
    Format standard citation:
    'NCERT Class 10 Science, Ch <no> <title>, <section heading>, p.<page> (chunk <id>)'
    """
    p_str = f"p.{page_start}" if page_start == page_end else f"pp.{page_start}-{page_end}"
    heading = section_heading or "Textbook Section"
    return f"NCERT Class 10 Science, Ch {chapter_no} {chapter_title}, {heading}, {p_str} (chunk {chunk_id})"

def clean_stem_for_subquestions(stem: str, sub_questions: Optional[List[Any]] = None) -> str:
    """
    Ensure the stem for a multi-part question contains only the scenario/lead-in passage,
    preventing duplicate question wording where subquestions are repeated in both the
    introductory paragraph and the numbered subparts (as in Q11).
    """
    if not stem:
        return "Answer the following questions:"
    clean = stem.strip()

    # 1. Match subpart markers like (a), (i), (1), 1., etc.
    marker_match = re.search(r'(?:\s*\([a-dA-D1-4ivxIVX]+\)\s+|\s*[1-4]\.\s+)', clean)
    if marker_match:
        lead_in = clean[:marker_match.start()].strip()
        if len(lead_in) >= 10:
            clean = lead_in
        else:
            clean = "Answer the following questions:"

    # 2. Check if the text of the first subquestion is embedded in the stem
    if sub_questions and isinstance(sub_questions, list) and len(sub_questions) > 0:
        first_sq = sub_questions[0]
        if isinstance(first_sq, dict):
            sq_stem = first_sq.get("stem", "").strip()
            if sq_stem and len(sq_stem) >= 12 and sq_stem.lower() in clean.lower():
                idx = clean.lower().find(sq_stem.lower())
                lead_in = clean[:idx].strip()
                lead_in = re.sub(r'[\(\[]?[a-dA-D1-4ivxIVX]+[\)\]\.]?\s*$', '', lead_in).strip()
                if len(lead_in) >= 10:
                    clean = lead_in
                else:
                    clean = "Answer the following questions:"

    # 3. Clean any trailing dangling marker
    clean = re.sub(r'[\(\[]?[a-dA-D1-4ivxIVX]+[\)\]\.]?\s*$', '', clean).strip()
    return format_science_text(clean)

def sanitize_question_content(content: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize all text fields in a question content dict:
    - Format science expressions (chemical formulas, pi -> π, d^2 -> d², I^2R -> I²R, * -> ×, Ω)
    - Strip option prefixes
    - Clean sub-question duplicate lead-ins (no duplicate subquestion wording in stem)
    - Split lumped multi-mark steps in marking scheme (split 2-mark lumps into 1+1)
    - Enforce integer step marks ("1 mark", no 0.5/1.5 splits)
    - Ensure MCQ marking scheme is concise: 'Correct option (X): 1 mark — <reason>'
    """
    if not isinstance(content, dict):
        return content

    sanitized = dict(content)

    # Sub-question lead-in deduplication:
    # If sub_questions are present, remove duplicated subquestions from the stem
    if "sub_questions" in sanitized and isinstance(sanitized["sub_questions"], list) and len(sanitized["sub_questions"]) >= 1:
        sanitized["stem"] = clean_stem_for_subquestions(sanitized.get("stem", ""), sanitized["sub_questions"])
    elif "stem" in sanitized and isinstance(sanitized["stem"], str):
        sanitized["stem"] = format_science_text(sanitized["stem"])

    if "answer" in sanitized and isinstance(sanitized["answer"], str):
        sanitized["answer"] = format_science_text(sanitized["answer"])

    if "options" in sanitized and isinstance(sanitized["options"], list):
        sanitized["options"] = [
            format_science_text(strip_option_prefix(opt))
            for opt in sanitized["options"]
        ]

    if "sub_questions" in sanitized and isinstance(sanitized["sub_questions"], list):
        clean_subs = []
        for sq in sanitized["sub_questions"]:
            if isinstance(sq, dict):
                sq_copy = dict(sq)
                if "stem" in sq_copy:
                    sq_copy["stem"] = format_science_text(strip_sub_question_prefix(sq_copy["stem"]))
                if "answer" in sq_copy:
                    sq_copy["answer"] = format_science_text(sq_copy["answer"])
                if "marks" in sq_copy and isinstance(sq_copy["marks"], (int, float)):
                    sq_copy["marks"] = int(sq_copy["marks"]) if sq_copy["marks"] == int(sq_copy["marks"]) else sq_copy["marks"]
                clean_subs.append(sq_copy)
            else:
                clean_subs.append(sq)
        sanitized["sub_questions"] = clean_subs

    # Sanitize and normalize marking scheme steps: strictly 1 mark per step (no 0.5/1.5 splits)
    if "marking_scheme" in sanitized and isinstance(sanitized["marking_scheme"], list):
        clean_ms = []
        q_type = sanitized.get("type", "")
        corr_opt = sanitized.get("correct_option")

        # For MCQs: enforce single step 'Correct option (X): 1 mark — <reason>'
        if q_type in ["mcq", "assertion_reason"] and corr_opt:
            ms_list = sanitized["marking_scheme"]
            first_step = ms_list[0] if ms_list and isinstance(ms_list[0], dict) else {}
            step_text = str(first_step.get("step", "")).strip()
            if len(step_text) > 160:
                step_text = step_text.split(".")[0] + "."
            step_text = re.sub(r'^(?:Correct\s+option\s*\(?[A-D]\)?[\:\s\-]*)?', '', step_text, flags=re.IGNORECASE).strip()
            # Strip any trailing mark suffix like ': 1 mark' or '[1 mark]'
            step_text = re.sub(r'(?::\s*|\s*—\s*|\s*\[)\s*\d+(?:\.\d+)?\s*(?:mark|marks)\s*\]?$', '', step_text, flags=re.IGNORECASE).strip()
            if not step_text:
                step_text = sanitized.get("answer", "Identification of correct scientific concept.")
            clean_ms = [{
                "step": f"Correct option ({corr_opt}): 1 mark — {format_science_text(step_text)}",
                "marks": 1
            }]
        else:
            for step in sanitized["marking_scheme"]:
                if isinstance(step, dict):
                    raw_st = str(step.get("step", ""))
                    # Strip trailing mark suffix like ': 0.5 mark' or '[1 mark]' from the description text
                    clean_st = re.sub(r'(?::\s*|\s*—\s*|\s*\[)\s*\d+(?:\.\d+)?\s*(?:mark|marks)\s*\]?$', '', raw_st, flags=re.IGNORECASE).strip()
                    clean_st = format_science_text(clean_st)

                    m = step.get("marks", 1)
                    m_val = int(m) if m == int(m) else (1 if float(m) <= 1.0 else 2)

                    # If step is lumped as 2 marks, try splitting into two 1-mark steps
                    if m_val == 2 and any(sep in clean_st for sep in [" and ", "; ", " / ", " as well as "]):
                        parts = re.split(r'\s+and\s+|\s*;\s*|\s+as well as\s+', clean_st, maxsplit=1)
                        if len(parts) == 2 and len(parts[0].strip()) > 8 and len(parts[1].strip()) > 8:
                            clean_ms.append({"step": parts[0].strip(), "marks": 1})
                            clean_ms.append({"step": parts[1].strip(), "marks": 1})
                            continue

                    clean_ms.append({"step": clean_st, "marks": 1})
                else:
                    clean_ms.append(step)

        sanitized["marking_scheme"] = clean_ms

    return sanitized
