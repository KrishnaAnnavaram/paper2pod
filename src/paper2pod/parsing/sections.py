"""Heuristic section splitter for paper text.

Recognises numbered headings ("1 Introduction", "3.2 Pruning Rule", "IV. RESULTS", "A. Proofs")
as well as common unnumbered ones ("Abstract", "Related Work"). Back matter (references,
acknowledgements, appendices) is removed so it never reaches the script writer.
"""
from __future__ import annotations

import re

from ..models import Section
from .cleaning import clean_text, unwrap_lines

KNOWN_HEADINGS = {
    "abstract", "introduction", "background", "related work", "preliminaries", "method", "methods",
    "methodology", "approach", "model", "model architecture", "architecture", "experiments",
    "experimental setup", "experimental results", "setup", "results", "evaluation", "analysis",
    "discussion", "limitations", "future work", "conclusion", "conclusions", "summary",
    "conclusion and future work", "discussion and limitations", "references", "bibliography",
    "acknowledgments", "acknowledgements", "appendix", "supplementary material", "broader impact",
    "ethics statement",
}
BACK_MATTER = ("references", "bibliography", "acknowledgments", "acknowledgements", "appendix",
               "appendices", "supplementary material", "checklist")

_NUMBERED = re.compile(
    r"^(?P<num>\d{1,2}(?:\.\d{1,2}){0,3}\.?|[IVX]{1,5}\.|[A-H]\.?)\s+(?P<title>[A-Z][^\n]{1,80})$"
)
_APPENDIX = re.compile(r"^appendix(?:\s+[A-Z0-9]{1,3})?\b", re.I)
_BAD_TITLE_CHARS = re.compile(r"[=<>{}\[\]|@%$]|\d+\.\d+|https?:")


def _title_case_ok(title: str) -> bool:
    words = title.split()
    if not 1 <= len(words) <= 9:
        return False
    if title[-1] in ".,;:" or _BAD_TITLE_CHARS.search(title):
        return False
    return True


def detect_heading(line: str) -> str | None:
    """Return the heading title if ``line`` looks like a section heading, else ``None``."""
    line = line.strip()
    if not line or len(line) > 90:
        return None
    bare = line.rstrip(":").strip()
    if bare.lower() in KNOWN_HEADINGS:
        return bare.title() if bare.isupper() else bare
    if _APPENDIX.match(bare) and len(bare.split()) <= 8:
        return bare
    match = _NUMBERED.match(line)
    if not match:
        return None
    num, title = match.group("num"), match.group("title").strip()
    if not _title_case_ok(title):
        return None
    if re.fullmatch(r"[A-H]\.?", num) and title.lower().split()[0] not in {"proof", "proofs", "extra",
                                                                         "additional", "details"}:
        # single-letter numbering is mostly used for appendices; avoid matching initials ("A. Smith")
        if not title.isupper():
            return None
    return title.title() if title.isupper() else title


def is_back_matter(title: str) -> bool:
    lowered = title.lower().strip()
    return lowered.startswith(BACK_MATTER) or bool(_APPENDIX.match(lowered))


def split_sections(text: str) -> list[Section]:
    """Split cleaned text into sections. Text before the first heading becomes a "Front matter" section."""
    sections: list[Section] = []
    title, buffer = "Front matter", []
    for line in (text or "").split("\n"):
        heading = detect_heading(line)
        if heading:
            if any(b.strip() for b in buffer):
                sections.append(Section(title, "\n".join(buffer).strip()))
            title, buffer = heading, []
        else:
            buffer.append(line)
    if any(b.strip() for b in buffer):
        sections.append(Section(title, "\n".join(buffer).strip()))
    return sections


def drop_back_matter(sections: list[Section]) -> list[Section]:
    """Remove references, acknowledgements and appendices, and everything after the references."""
    kept: list[Section] = []
    for section in sections:
        if section.title.lower().startswith(("references", "bibliography")):
            break
        if is_back_matter(section.title):
            continue
        kept.append(section)
    return kept


def paper_sections(raw_text: str, min_words: int = 15) -> list[Section]:
    """Full parsing step: clean -> split -> drop back matter -> unwrap -> drop near-empty sections."""
    sections = drop_back_matter(split_sections(clean_text(raw_text)))
    result = []
    for section in sections:
        body = unwrap_lines(section.text)
        if Section(section.title, body).words >= min_words:
            result.append(Section(section.title, body))
    return result
