"""Deterministic offline stand-ins for the LLM and TTS services.

They power ``paper2pod demo`` and the test-suite: no network, no keys, same output every run.
The fake LLM writes dialogue only from sentences found in its notes, so the grounding check
should pass, and it honours the requested word budget so the length controller can be tested.
"""
from __future__ import annotations

import math
import re
import zlib
from array import array
from typing import Any

from ..text_utils import count_words, split_sentences
from .llm import LLMResult

_TAG = r"<{0}>\s*(.*?)\s*</{0}>"
_LABEL = re.compile(r"^(?:[-•]\s*)?(?:(?:Title|Abstract|What's ahead|Key takeaways to recap):\s*)?")

QUESTIONS = (
    "Okay, walk me through that.",
    "Why does that matter?",
    "Can you unpack that a little?",
    "And what did they find?",
    "How should listeners picture that?",
    "What is the catch?",
)
BRIDGES = (
    "Right, that is the key point.",
    "That makes sense.",
    "Good question.",
    "Let me put it simply.",
)


def _extract(tag: str, text: str) -> str:
    match = re.search(_TAG.format(tag), text, re.S)
    return match.group(1) if match else ""


def _note_sentences(notes: str) -> list[str]:
    sentences: list[str] = []
    for line in notes.splitlines():
        line = _LABEL.sub("", line.strip())
        sentences.extend(s for s in split_sentences(line) if count_words(s) >= 4)
    return sentences


def _clip(text: str, words: int) -> str:
    tokens = text.split()
    if len(tokens) <= words:
        return text
    return " ".join(tokens[:words]).rstrip(",;:") + "."


class FakeLLM:
    name = "fake-llm"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, *, task: str, system: str, user: str, schema: dict[str, Any],
                      max_tokens: int) -> LLMResult:
        self.calls.append({"task": task, "max_tokens": max_tokens, "user": user})
        if task == "summarize_section":
            data = self._summarize(user)
        elif task == "write_segment":
            data = self._segment(user)
        else:
            raise ValueError(f"FakeLLM does not know task {task!r}")
        words = sum(count_words(str(v)) for v in data.values())
        return LLMResult(data=data, prompt_tokens=len(user) // 4, completion_tokens=int(words * 1.4))

    @staticmethod
    def _summarize(user: str) -> dict[str, Any]:
        sentences = split_sentences(" ".join(_extract("section", user).split()))
        summary = " ".join(sentences[:2])
        with_numbers = [s for s in sentences[2:] if re.search(r"\d", s)]
        others = [s for s in sentences[2:] if s not in with_numbers]
        return {"summary": summary, "key_points": (with_numbers + others)[:4]}

    @staticmethod
    def _segment(user: str) -> dict[str, Any]:
        target = int(re.search(r"Target length: (\d+) words", user).group(1))
        speakers_raw = re.search(r"^Speakers: (.+)$", user, re.M).group(1)
        names = [part.split(" [")[0].strip() for part in speakers_raw.split("; ")]
        kind = re.search(r"^Segment \d+ of \d+: .* \((intro|body|outro)\)$", user, re.M).group(1)
        title = re.search(r"^Podcast about: (.+)$", user, re.M).group(1).strip()
        facts = _note_sentences(_extract("notes", user)) or [f"This part is about {title}."]

        host, others = names[0], names[1:]
        lines: list[tuple[str, str]] = []
        if kind == "intro":
            lines.append((host, f"Welcome to the show. I'm {host}, and today I'm joined by "
                                f"{' and '.join(others)}. We are talking about {title}."))
        elif kind == "outro":
            lines.append((host, "Let's wrap up with the main takeaways."))
        i = 0
        while sum(count_words(t) for _, t in lines) < target:
            explainer = others[i % len(others)]
            if i % 2 == 0:
                lines.append((host, QUESTIONS[i % len(QUESTIONS)]))
            lines.append((explainer, f"{BRIDGES[i % len(BRIDGES)]} {facts[i % len(facts)]}"))
            i += 1
            if i > 500:
                break
        if kind == "outro":
            lines.append((host, "Thanks for listening."))

        turns, used = [], 0
        for speaker, text in lines:
            room = target - used
            if room <= 0:
                break
            if count_words(text) > room:
                if room < 3:
                    break
                text = _clip(text, room)
            turns.append({"speaker": speaker, "text": text, "direction": None})
            used += count_words(text)
        return {"turns": turns}


class FakeTTS:
    """Writes a soft tone per voice; duration follows the word count at ``words_per_minute``."""

    name = "fake-tts"
    max_chars = 4000

    def __init__(self, sample_rate: int = 8000, words_per_minute: int = 150):
        self.sample_rate = sample_rate
        self.words_per_minute = words_per_minute
        self.calls: list[tuple[str, int]] = []
        self._tones: dict[str, bytes] = {}

    def _tone(self, voice: str) -> bytes:
        if voice not in self._tones:
            freq = 140 + zlib.crc32(voice.encode()) % 180  # whole Hz, so a 1 s buffer loops seamlessly
            amp = 0.15 * 32767
            samples = array("h", (int(amp * math.sin(2 * math.pi * freq * n / self.sample_rate))
                                  for n in range(self.sample_rate)))
            self._tones[voice] = samples.tobytes()
        return self._tones[voice]

    def synthesize(self, text: str, voice: str) -> bytes:
        if len(text) > self.max_chars:
            raise ValueError("text exceeds max_chars; chunk it first")
        self.calls.append((voice, len(text)))
        seconds = count_words(text) * 60.0 / self.words_per_minute
        n_bytes = int(seconds * self.sample_rate) * 2
        tone = self._tone(voice)
        repeats = n_bytes // len(tone) + 1
        return (tone * repeats)[:n_bytes]
