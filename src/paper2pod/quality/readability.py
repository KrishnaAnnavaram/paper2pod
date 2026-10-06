"""Readability and jargon density of the spoken script."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from ..models import Script
from ..text_utils import split_sentences

_WORD = re.compile(r"[A-Za-z]+(?:'[a-z]+)?")
_VOWEL_GROUPS = re.compile(r"[aeiouy]+")


def syllables(word: str) -> int:
    word = word.lower()
    count = len(_VOWEL_GROUPS.findall(word))
    if word.endswith("e") and not word.endswith(("le", "ee")) and count > 1:
        count -= 1
    return max(1, count)


@dataclass
class ReadabilityReport:
    flesch_reading_ease: float
    avg_sentence_words: float
    jargon_rate: float  # share of words that are acronyms or very long

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def readability(script: Script) -> ReadabilityReport:
    text = " ".join(t.text for t in script.turns)
    sentences = max(1, len(split_sentences(text)))
    words = _WORD.findall(text)
    if not words:
        return ReadabilityReport(0.0, 0.0, 0.0)
    syllable_total = sum(syllables(w) for w in words)
    flesch = 206.835 - 1.015 * (len(words) / sentences) - 84.6 * (syllable_total / len(words))
    jargon = sum(1 for w in words if (w.isupper() and len(w) > 1) or len(w) >= 13)
    return ReadabilityReport(round(flesch, 1), round(len(words) / sentences, 1), round(jargon / len(words), 4))
