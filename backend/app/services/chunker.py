import re
import unicodedata
from typing import List, Dict, Any, Optional, Tuple
from app.config import settings
from app.services.llm import count_tokens

# Patterns to identify section breaks and headings
SECTION_HEADING_REGEX = re.compile(
    r'^(?:'
    r'#{1,6}\s+(.+)|'                                 # Markdown headings # Heading
    r'(?:[0-9]{1,2}\.[0-9]{1,2}(?:\.[0-9]+)?\s+.+)|'   # 1.1 Chemical Equations
    r'(?:Activity\s+[0-9]{1,2}\.[0-9]{1,2}.*)|'        # Activity 1.1
    r'(?:Example\s+[0-9]{1,2}\.[0-9]{1,2}.*)|'         # Example 11.1
    r'(?:Questions(?:\s+.*)?)|'                        # Questions
    r'(?:Exercises(?:\s+.*)?)|'                        # Exercises
    r'(?:What you have learnt.*)|'                     # Summary
    r'(?:Summary.*)'                                   # Summary
    r')$',
    re.IGNORECASE | re.MULTILINE
)

def clean_page_text(text: str) -> str:
    """Clean raw text extracted from a PDF page."""
    if not text:
        return ""

    # Normalize unicode to NFKC
    text = unicodedata.normalize("NFKC", text)

    # Replace unicode replacement character if present
    text = text.replace("\ufffd", "'")

    # Remove headers/footers like 'Rationalised 2023-24' or lonely page numbers
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        # Drop lines that are just numbers (standalone page numbers)
        if stripped.isdigit() and len(stripped) <= 3:
            continue
        # Drop standard NCERT publication stamps and running headers
        if re.search(r'(?:rationali[sz]ed|reprint)\s+20\d\d-\d\d', stripped, re.IGNORECASE):
            continue
        if stripped.lower() in ["science", "reprint", ""]:
            continue
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # Re-join hyphenated words across lines
    text = re.sub(r'(\b[a-zA-Z]+)-\s*\n\s*([a-zA-Z]+\b)', r'\1\2', text)

    # Normalize multiple newlines and spaces
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]+', ' ', text)

    return text.strip()

def determine_content_type(heading: str, text: str) -> str:
    """Classify chunk content type based on heading and text content."""
    h_clean = heading.strip().strip("*# ").lower()
    t_start = text.strip()[:60].lower()

    if "activity" in h_clean or re.match(r'^activity\s+\d', t_start):
        return "activity"
    if "question" in h_clean or "exercise" in h_clean or re.match(r'^(?:questions|exercises)\b', t_start):
        return "exercise"
    if "example" in h_clean or re.match(r'^example\s+\d', t_start):
        return "example"
    if "what you have learnt" in h_clean or "summary" in h_clean:
        return "summary"
    return "concept"

def split_long_text(text: str, target_tokens: int, max_tokens: int, overlap_tokens: int) -> List[str]:
    """Split a long text block into overlapping sub-chunks strictly within max_tokens."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [text.strip()]

    chunks: List[str] = []
    current_parts: List[str] = []

    for para in paragraphs:
        candidate = "\n\n".join(current_parts + [para])
        cand_tokens = count_tokens(candidate)

        if cand_tokens <= max_tokens:
            current_parts.append(para)
        else:
            if current_parts:
                chunks.append("\n\n".join(current_parts))
                # Create overlap using last paragraph if small enough
                overlap_text = current_parts[-1]
                if count_tokens(overlap_text) <= overlap_tokens and count_tokens(overlap_text + "\n\n" + para) <= max_tokens:
                    current_parts = [overlap_text, para]
                else:
                    current_parts = [para]
            else:
                # If block has newlines (e.g. markdown table or list), split by lines
                if "\n" in para:
                    sub_units = [line for line in para.split("\n") if line.strip()]
                    separator = "\n"
                else:
                    sub_units = re.split(r'(?<=[.!?])\s+', para)
                    separator = " "

                s_parts: List[str] = []
                for s in sub_units:
                    s_candidate = separator.join(s_parts + [s])
                    if count_tokens(s_candidate) <= max_tokens:
                        s_parts.append(s)
                    else:
                        if s_parts:
                            chunks.append(separator.join(s_parts))
                            s_parts = [s]
                        else:
                            chunks.append(s)
                            s_parts = []
                if s_parts:
                    current_parts = [separator.join(s_parts)]
                else:
                    current_parts = []

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    # Merge tiny last chunk into previous only if it stays strictly within max_tokens
    if len(chunks) > 1 and count_tokens(chunks[-1]) < 40:
        if count_tokens(chunks[-2] + "\n\n" + chunks[-1]) <= max_tokens:
            last = chunks.pop()
            chunks[-1] = chunks[-1] + "\n\n" + last

    return chunks

def chunk_markdown_pages(pages_data: List[Dict[str, Any]], chapter_no: int) -> List[Dict[str, Any]]:
    """
    Take page-by-page markdown output from pymupdf4llm, split by headings/sections,
    and enforce token bounds.
    """
    # 1. Collect stream of sections with page tracking
    sections: List[Dict[str, Any]] = []
    current_heading = "Introduction"
    current_text_blocks: List[str] = []
    start_page = 1
    current_page = 1

    for page_idx, page in enumerate(pages_data):
        page_num = page.get("metadata", {}).get("page_number", page_idx + 1)
        raw_text = page.get("text", "")
        # Normalize spaced out section words like Q U E S T I O N S
        raw_text = re.sub(r'\bQ\s+U\s+E\s+S\s+T\s+I\s+O\s+N\s+S\b', 'Questions', raw_text, flags=re.IGNORECASE)
        raw_text = re.sub(r'\bE\s+X\s+E\s+R\s+C\s+I\s+S\s+E\s+S\b', 'Exercises', raw_text, flags=re.IGNORECASE)
        cleaned = clean_page_text(raw_text)
        if not cleaned:
            continue

        current_page = page_num
        lines = cleaned.split("\n")

        for line in lines:
            line_str = line.strip()
            # Check if this line is a heading/section break
            match = SECTION_HEADING_REGEX.match(line_str)
            if match and len(line_str) < 120:
                clean_heading = re.sub(r'^#+\s*', '', line_str).strip()
                clean_heading = re.sub(r'^\*+|\*+$', '', clean_heading).strip()

                # Ignore punctuation/short symbols and Solution headers
                if len(clean_heading) < 3 or clean_heading in ["?", "??", "***", "---"] or clean_heading.lower().startswith("solution"):
                    current_text_blocks.append(line)
                    continue

                # Drop CHAPTER banners like 'CHAPTER11 Electricity' and sentence fragments
                if re.match(r'^CHAPTER\s*\d+', clean_heading, re.IGNORECASE):
                    current_text_blocks.append(line)
                    continue

                if any(frag in clean_heading.lower() for frag in ["we get", "we have", "let us", "[eq.", "(eq.", "applying", "substituting", "according to"]) or clean_heading.endswith((",", ";", ":")):
                    current_text_blocks.append(line)
                    continue

                # If we have accumulated text, save current section
                if current_text_blocks:
                    full_sec_text = "\n".join(current_text_blocks).strip()
                    if full_sec_text:
                        sections.append({
                            "heading": current_heading,
                            "text": full_sec_text,
                            "page_start": start_page,
                            "page_end": current_page,
                        })
                    current_text_blocks = []

                # New heading starts
                current_heading = clean_heading if clean_heading else line_str
                start_page = current_page
            else:
                current_text_blocks.append(line)

    # Flush last section
    if current_text_blocks:
        full_sec_text = "\n".join(current_text_blocks).strip()
        if full_sec_text:
            sections.append({
                "heading": current_heading,
                "text": full_sec_text,
                "page_start": start_page,
                "page_end": current_page,
            })

    # 2. Re-chunk sections exceeding CHUNK_MAX_TOKENS and merge tiny fragments
    final_chunks: List[Dict[str, Any]] = []

    for sec in sections:
        sec_text = sec["text"]
        t_count = count_tokens(sec_text)
        content_type = determine_content_type(sec["heading"], sec_text)

        if t_count <= settings.CHUNK_MAX_TOKENS:
            final_chunks.append({
                "chapter_no": chapter_no,
                "page_start": sec["page_start"],
                "page_end": sec["page_end"],
                "section_heading": sec["heading"][:255],
                "content_type": content_type,
                "text": sec_text,
                "token_count": t_count,
            })
        else:
            # Sub-split long section
            sub_texts = split_long_text(
                sec_text,
                target_tokens=settings.CHUNK_TARGET_TOKENS,
                max_tokens=settings.CHUNK_MAX_TOKENS,
                overlap_tokens=settings.CHUNK_OVERLAP_TOKENS,
            )
            for sub in sub_texts:
                final_chunks.append({
                    "chapter_no": chapter_no,
                    "page_start": sec["page_start"],
                    "page_end": sec["page_end"],
                    "section_heading": sec["heading"][:255],
                    "content_type": content_type,
                    "text": sub,
                    "token_count": count_tokens(sub),
                })

    # 3. Merge tiny fragments (< 40 tokens) into neighbors to satisfy the QA gate (<3% under 40 tokens)
    if not final_chunks:
        return []

    # Forward merge for the first chunk if tiny
    merged_pass: List[Dict[str, Any]] = []
    idx = 0
    if len(final_chunks) > 1 and final_chunks[0]["token_count"] < 40 and final_chunks[0]["content_type"] == final_chunks[1]["content_type"]:
        combined_text = final_chunks[0]["text"] + "\n\n" + final_chunks[1]["text"]
        if count_tokens(combined_text) <= settings.CHUNK_MAX_TOKENS:
            final_chunks[1]["text"] = combined_text
            final_chunks[1]["page_start"] = min(final_chunks[0]["page_start"], final_chunks[1]["page_start"])
            final_chunks[1]["token_count"] = count_tokens(combined_text)
            idx = 1

    while idx < len(final_chunks):
        c = final_chunks[idx]
        should_merge = False
        if merged_pass and c["token_count"] < 40:
            if merged_pass[-1]["content_type"] == c["content_type"]:
                should_merge = True
            elif c["content_type"] == "concept" and c["token_count"] <= 35:
                should_merge = True

        if should_merge:
            comb = merged_pass[-1]["text"] + "\n\n" + c["text"]
            if count_tokens(comb) <= settings.CHUNK_MAX_TOKENS:
                merged_pass[-1]["text"] = comb
                merged_pass[-1]["page_end"] = max(merged_pass[-1]["page_end"], c["page_end"])
                merged_pass[-1]["token_count"] = count_tokens(comb)
            else:
                merged_pass.append(c)
        else:
            merged_pass.append(c)
        idx += 1

    return merged_pass
