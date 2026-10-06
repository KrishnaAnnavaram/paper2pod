"""Small text helpers used by several stages."""
from __future__ import annotations

import re

_WORD = re.compile(r"[A-Za-z0-9À-ɏ]+(?:['’\-.][A-Za-z0-9À-ɏ]+)*")
_SENTENCE_END = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])")


def count_words(text: str) -> int:
    """Count spoken words. Hyphenated and dotted tokens (``state-of-the-art``, ``28.4``) count once."""
    return len(_WORD.findall(text or ""))


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences on terminal punctuation followed by a capital or digit."""
    text = " ".join((text or "").split())
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


_EMPHASIS = re.compile(r"(\*{1,3}|_{2,3})(?=\S)(.+?)(?<=\S)\1")
_STRAY_ASTERISKS = re.compile(r"\*+")
_LEADING_MARKUP = re.compile(r"^\s*(?:#{1,6}\s+|[-•]\s+|>\s+)")
# Only well-known, bracketed delivery cues are treated as directions. Parentheses are never touched,
# so "(BERT)" or "(x + y)" stay in the spoken text.
_CUE_WORDS = ("laughs", "laughing", "chuckles", "chuckling", "sighs", "pause", "pauses", "music",
              "intro music", "outro music", "applause", "clears throat", "giggles", "smiles")
_BRACKET_CUE = re.compile(r"\[\s*(" + "|".join(_CUE_WORDS) + r")\s*\]", re.I)


def strip_markup(text: str, speaker_names: list[str] | tuple[str, ...] = ()) -> tuple[str, str | None]:
    """Clean one line of dialogue for speech.

    Returns ``(text, cue)``: markdown emphasis markers are removed but the emphasised words are
    kept, a leading ``Name:`` label is dropped, and a bracketed cue such as ``[laughs]`` is moved
    out of the text into ``cue``. Content inside parentheses is never removed.
    """
    text = (text or "").strip()
    for name in speaker_names:
        label = re.compile(r"^\W{0,3}" + re.escape(name) + r"\W{0,3}:\W{0,3}\s*", re.I)
        text = label.sub("", text, count=1)
    cues = [m.group(1).lower() for m in _BRACKET_CUE.finditer(text)]
    text = _BRACKET_CUE.sub(" ", text)
    text = _LEADING_MARKUP.sub("", text)
    previous = None
    while previous != text:  # nested emphasis such as ***word***
        previous, text = text, _EMPHASIS.sub(r"\2", text)
    text = _STRAY_ASTERISKS.sub("", text)
    text = " ".join(text.split())
    return text, (", ".join(cues) if cues else None)


def truncate_words(text: str, max_words: int) -> str:
    """Keep at most ``max_words`` words, cutting at the last full sentence when possible."""
    if count_words(text) <= max_words:
        return text
    kept: list[str] = []
    used = 0
    for sentence in split_sentences(text):
        n = count_words(sentence)
        if used + n > max_words:
            break
        kept.append(sentence)
        used += n
    if kept:
        return " ".join(kept)
    words = text.split()
    return " ".join(words[:max_words]).rstrip(",;:") + "."
