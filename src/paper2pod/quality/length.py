"""Length targets: word budget before synthesis, measured audio duration after."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..models import Script, Turn
from ..text_utils import truncate_words


@dataclass
class LengthReport:
    target_minutes: float
    target_words: int
    script_words: int
    estimated_minutes: float
    word_ratio: float
    within_tolerance: bool
    audio_minutes: float | None = None
    audio_ratio: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_length(script: Script, minutes: float, words_per_minute: int, tolerance: float,
                 audio_seconds: float | None = None) -> LengthReport:
    target_words = int(round(minutes * words_per_minute))
    words = script.words
    ratio = words / target_words if target_words else 0.0
    report = LengthReport(
        target_minutes=minutes,
        target_words=target_words,
        script_words=words,
        estimated_minutes=round(words / words_per_minute, 2),
        word_ratio=round(ratio, 3),
        within_tolerance=abs(ratio - 1) <= tolerance,
    )
    if audio_seconds is not None:
        report.audio_minutes = round(audio_seconds / 60, 2)
        report.audio_ratio = round(audio_seconds / 60 / minutes, 3) if minutes else None
    return report


def trim_turns(turns: list[Turn], max_words: int, min_last_turn_words: int = 6) -> list[Turn]:
    """Keep whole turns up to ``max_words``; shorten the turn that crosses the limit at a sentence end."""
    kept: list[Turn] = []
    used = 0
    for turn in turns:
        if used + turn.words <= max_words:
            kept.append(turn)
            used += turn.words
            continue
        room = max_words - used
        if room >= min_last_turn_words:
            text = truncate_words(turn.text, room)
            if text:
                kept.append(Turn(turn.speaker, text, turn.direction, turn.segment))
        break
    return kept
