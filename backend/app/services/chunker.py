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
        # Drop standard NCERT publication stamps
        if re.search(r'rationali[sz]ed\s+20\d\d-\d\d', stripped, re.IGNORECASE):
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
    combined = f"{heading} {text[:120]}".lower()

    if "activity" in combined:
        return "activity"
    if "question" in combined or "exercise" in combined:
        return "exercise"
    if "example" in combined:
        return "example"
    if "what you have learnt" in combined or "summary" in combined:
        return "summary"
    return "concept"

def split_long_text(text: str, target_tokens: int, max_tokens: int, overlap_tokens: int) -> List[str]:
    """Split a long text block into overlapping sub-chunks within max_tokens."""
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
                # Create overlap using last paragraph if possible
                overlap_text = current_parts[-1]
                if count_tokens(overlap_text) > overlap_tokens:
                    # Just start new chunk with para
                    current_parts = [para]
                else:
                    current_parts = [overlap_text, para]
            else:
                # Single paragraph is longer than max_tokens, split by sentences
                sentences = re.split(r'(?<=[.!?])\s+', para)
                s_parts: List[str] = []
                for s in sentences:
                    s_candidate = " ".join(s_parts + [s])
                    if count_tokens(s_candidate) <= max_tokens:
                        s_parts.append(s)
                    else:
                        if s_parts:
                            chunks.append(" ".join(s_parts))
                            s_parts = [s]
                        else:
                            # Even single sentence is huge, append it anyway
                            chunks.append(s)
                            s_parts = []
                if s_parts:
                    current_parts = [" ".join(s_parts)]
                else:
                    current_parts = []

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    # Merge tiny last chunk into previous if under 40 tokens
    if len(chunks) > 1 and count_tokens(chunks[-1]) < 40:
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
                clean_heading = re.sub(r'^#+\s*', '', line_str).strip()
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

    # 3. Merge any tiny fragment (< 40 tokens) into neighbor if they share the same content_type
    merged_chunks: List[Dict[str, Any]] = []
    for c in final_chunks:
        if merged_chunks and c["token_count"] < 40 and (merged_chunks[-1]["token_count"] + c["token_count"] <= settings.CHUNK_MAX_TOKENS):
            merged_chunks[-1]["text"] += "\n\n" + c["text"]
            merged_chunks[-1]["page_end"] = max(merged_chunks[-1]["page_end"], c["page_end"])
            merged_chunks[-1]["token_count"] = count_tokens(merged_chunks[-1]["text"])
        else:
            merged_chunks.append(c)

    return merged_chunks
