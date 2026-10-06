"""Clean raw PDF text: ligatures, hyphenation, page furniture and whitespace."""
from __future__ import annotations

import re
import unicodedata

_PAGE_NUMBER = re.compile(r"^\s*(?:page\s+)?\d{1,4}(?:\s*(?:/|of)\s*\d{1,4})?\s*$", re.I)
_ARXIV_STAMP = re.compile(r"^\s*arXiv:\d{4}\.\d{4,5}(?:v\d+)?\s*\[[^\]]+\].*$")
_HYPHEN_BREAK = re.compile(r"(?<=[a-z])-\n(?=[a-z])")
_SPACES = re.compile(r"[ \t ]+")


def clean_text(raw: str) -> str:
    """Normalise text extracted from a PDF while keeping line structure (needed for headings).

    - NFKC normalisation turns ligatures such as U+FB01 into plain "fi".
    - Words split across lines with a hyphen are re-joined ("repre-\\nsentation").
    - Bare page numbers and the vertical arXiv stamp line are removed.
    """
    text = unicodedata.normalize("NFKC", raw or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "\n")
    text = _HYPHEN_BREAK.sub("", text)
    lines = []
    for line in text.split("\n"):
        line = _SPACES.sub(" ", line).strip()
        if _PAGE_NUMBER.match(line) or _ARXIV_STAMP.match(line):
            continue
        lines.append(line)
    text = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def unwrap_lines(text: str) -> str:
    """Join hard-wrapped lines into paragraphs; blank lines stay paragraph breaks."""
    paragraphs = re.split(r"\n\s*\n", text or "")
    return "\n\n".join(" ".join(p.split()) for p in paragraphs if p.strip())
