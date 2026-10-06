"""Section-aware outline (map-reduce): each part of the paper is summarised on its own.

This replaces "send the first N characters of the PDF": every section contributes, long sections
are chunked, and back matter has already been removed by the parser.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from ..models import Paper, Section
from ..services.llm import LLM
from ..text_utils import count_words, split_sentences
from .budget import max_tokens_for_words
from .prompts import render

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_points": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "key_points"],
    "additionalProperties": False,
}


@dataclass
class OutlineItem:
    title: str
    summary: str
    key_points: list[str] = field(default_factory=list)
    weight: float = 1.0

    def notes(self) -> str:
        points = "\n".join(f"- {p}" for p in self.key_points)
        return f"{self.summary}\n{points}".strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def group_sections(sections: list[Section], max_items: int = 8, min_words: int = 120) -> list[Section]:
    """Merge sub-sections and tiny sections so the outline has at most ``max_items`` parts."""
    body = [s for s in sections if s.title.lower() not in {"abstract", "front matter"}]
    groups: list[Section] = []
    for section in body:
        if groups and groups[-1].words < min_words:
            last = groups[-1]
            groups[-1] = Section(f"{last.title} / {section.title}", f"{last.text}\n\n{section.text}")
        else:
            groups.append(Section(section.title, section.text))
    while len(groups) > max(1, max_items):
        # merge the adjacent pair with the fewest words combined
        i = min(range(len(groups) - 1), key=lambda k: groups[k].words + groups[k + 1].words)
        a, b = groups[i], groups[i + 1]
        groups[i : i + 2] = [Section(f"{a.title} / {b.title}", f"{a.text}\n\n{b.text}")]
    return groups


def chunk_text(text: str, max_chars: int) -> list[str]:
    """Split ``text`` into pieces of at most ``max_chars``, on sentence boundaries where possible."""
    if len(text) <= max_chars:
        return [text]
    chunks, current = [], ""
    for sentence in split_sentences(text):
        while len(sentence) > max_chars:  # pathological: one enormous "sentence"
            head, sentence = sentence[:max_chars], sentence[max_chars:]
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head)
        if current and len(current) + 1 + len(sentence) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def build_outline(paper: Paper, sections: list[Section], llm: LLM, *, max_items: int = 8,
                  chunk_chars: int = 12_000, summary_words: int = 140,
                  on_item: Callable[[int, int], None] | None = None,
                  check_cancel: Callable[[], None] | None = None) -> list[OutlineItem]:
    groups = group_sections(sections, max_items=max_items)
    if not groups:
        if not paper.abstract:
            raise ValueError("no usable text: the paper has no parsable sections and no abstract")
        groups = [Section("Overview", paper.abstract)]

    system = render("summarize_system")
    outline: list[OutlineItem] = []
    for n, group in enumerate(groups, start=1):
        summaries: list[str] = []
        points: list[str] = []
        for chunk in chunk_text(group.text, chunk_chars):
            if check_cancel:
                check_cancel()
            user = render("summarize_user", paper_title=paper.title, section_title=group.title,
                          text=chunk, max_words=summary_words)
            result = llm.complete_json(task="summarize_section", system=system, user=user,
                                       schema=SUMMARY_SCHEMA, max_tokens=max_tokens_for_words(summary_words * 2))
            summaries.append(str(result.data.get("summary", "")).strip())
            points.extend(str(p).strip() for p in result.data.get("key_points", []) if str(p).strip())
        outline.append(OutlineItem(
            title=group.title,
            summary=" ".join(s for s in summaries if s),
            key_points=points[:8],
            weight=math.sqrt(max(count_words(group.text), 1)),
        ))
        if on_item:
            on_item(n, len(groups))
    return outline
