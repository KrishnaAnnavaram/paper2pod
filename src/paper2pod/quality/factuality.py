"""Grounding check: are the numbers and acronyms in the script present in the paper?

This is a cheap, deterministic, lexical check. It catches the most damaging kind of hallucination
in an explainer (made-up results, wrong figures, invented method names) but it cannot judge
paraphrased claims. Treat a high score as "no obvious fabrication", not as proof of accuracy.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from ..models import Script
from ..text_utils import split_sentences

_NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*(?:\s?(?:%|percent\b))?")
_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]+(?:-[A-Z0-9]+)*\b")
CONVERSATIONAL = {"I", "OK", "AI", "US", "UK", "TV", "FAQ", "PHD", "PDF", "Q", "A"}


def _norm_number(token: str) -> str:
    token = token.lower().replace("percent", "%").replace(" ", "")
    token = re.sub(r"(?<=\d),(?=\d{3}\b)", "", token)  # 1,000 -> 1000
    return token


def _is_trivial_number(token: str) -> bool:
    """Small bare integers ("two ideas", "step 3") are conversational, not claims."""
    return token.isdigit() and int(token) < 10


def _numbers(text: str) -> set[str]:
    return {_norm_number(m.group(0)) for m in _NUMBER.finditer(text)}


def _acronyms(text: str) -> set[str]:
    found = set()
    for match in _ACRONYM.finditer(text):
        token = match.group(0)
        if len(token) >= 2 and token.upper() not in CONVERSATIONAL and not token.isdigit():
            found.add(token)
    return found


@dataclass
class GroundingReport:
    checked_sentences: int = 0
    supported_sentences: int = 0
    unsupported: list[dict[str, Any]] = field(default_factory=list)

    @property
    def score(self) -> float:
        return 1.0 if not self.checked_sentences else self.supported_sentences / self.checked_sentences

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["score"] = round(self.score, 3)
        return data


def check_grounding(script: Script, paper_text: str) -> GroundingReport:
    paper_numbers = _numbers(paper_text)
    # a percentage in the script may be written without "%" in a table, and vice versa
    paper_numbers |= {n.rstrip("%") for n in paper_numbers}
    paper_acronyms = _acronyms(paper_text)
    report = GroundingReport()
    for index, turn in enumerate(script.turns):
        for sentence in split_sentences(turn.text):
            numbers = {n for n in _numbers(sentence) if not _is_trivial_number(n)}
            acronyms = _acronyms(sentence)
            if not numbers and not acronyms:
                continue
            report.checked_sentences += 1
            missing = sorted(n for n in numbers if n not in paper_numbers and n.rstrip("%") not in paper_numbers)
            missing += sorted(a for a in acronyms if a not in paper_acronyms and a.rstrip("s") not in paper_acronyms)
            if missing:
                report.unsupported.append({"turn": index, "speaker": turn.speaker, "tokens": missing,
                                           "sentence": sentence})
            else:
                report.supported_sentences += 1
    return report
