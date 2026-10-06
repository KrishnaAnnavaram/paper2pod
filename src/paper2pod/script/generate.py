"""Structured, length-controlled dialogue generation.

The script is produced one segment at a time. Each segment is a JSON list of turns
(``speaker``, ``text``, ``direction``) validated against the speaker list. Segments that miss
their word budget are regenerated with explicit feedback; output that is still too long is
trimmed at a sentence boundary, so the final length stays close to the requested duration.
"""
from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from typing import Any, Callable

from ..errors import ScriptFormatError
from ..models import Paper, Script, Speaker, Turn
from ..quality.length import trim_turns
from ..services.llm import LLM
from ..text_utils import strip_markup, truncate_words
from .budget import MODEL_OUTPUT_LIMIT, SegmentPlan, plan_segments
from .outline import OutlineItem
from .prompts import render

log = logging.getLogger(__name__)

SEGMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "turns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "speaker": {"type": "string"},
                    "text": {"type": "string"},
                    "direction": {"type": ["string", "null"]},
                },
                "required": ["speaker", "text", "direction"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["turns"],
    "additionalProperties": False,
}

ROLE_HINTS = {
    "host": "guides the conversation, asks clear questions, summarises",
    "expert": "explains the paper in depth with examples",
    "guest": "a curious newcomer who asks the questions listeners would ask",
}
POSITION_NOTES = {
    "intro": "Open the show: welcome listeners, introduce the speakers by name and the paper, and preview "
             "what is ahead.",
    "body": "Continue the conversation naturally from the previous segment. Do not greet listeners again.",
    "outro": "Recap the key takeaways and the stated limitations, then close the show.",
}


def speakers_line(speakers: list[Speaker]) -> str:
    return "; ".join(f"{s.name} [{s.role}: {ROLE_HINTS.get(s.role, '')}]" for s in speakers)


def parse_turns(data: Any, speakers: list[Speaker], segment: int = 0) -> list[Turn]:
    """Validate a model response and convert it into ``Turn`` objects."""
    raw_turns = data.get("turns") if isinstance(data, dict) else None
    if not isinstance(raw_turns, list) or not raw_turns:
        raise ScriptFormatError("response has no 'turns' list")
    names = [s.name for s in speakers]
    lookup = {n.lower(): n for n in names}
    turns: list[Turn] = []
    for i, raw in enumerate(raw_turns):
        if not isinstance(raw, dict):
            raise ScriptFormatError(f"turn {i} is not an object")
        name = str(raw.get("speaker", "")).strip().strip("*:_ ").strip()
        canonical = lookup.get(name.lower())
        if canonical is None:
            raise ScriptFormatError(f"turn {i} has unknown speaker {name!r}; expected one of {names}")
        text, cue = strip_markup(str(raw.get("text", "")), names)
        direction = raw.get("direction")
        direction = str(direction).strip() if direction else None
        direction = ", ".join(d for d in (direction, cue) if d) or None
        if text:
            turns.append(Turn(speaker=canonical, text=text, direction=direction, segment=segment))
    if not turns:
        raise ScriptFormatError("all turns were empty")
    return turns


@dataclass
class SegmentReport:
    index: int
    title: str
    target_words: int
    actual_words: int
    attempts: int
    truncated_responses: int
    invalid_responses: int
    within_tolerance: bool
    trimmed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScriptWriter:
    def __init__(self, llm: LLM, *, words_per_minute: int = 150, tolerance: float = 0.12,
                 max_segment_words: int = 650, max_regenerations: int = 2):
        self.llm = llm
        self.words_per_minute = words_per_minute
        self.tolerance = tolerance
        self.max_segment_words = max_segment_words
        self.max_regenerations = max_regenerations

    def plan(self, paper: Paper, outline: list[OutlineItem], minutes: float) -> list[SegmentPlan]:
        return plan_segments(outline, minutes, self.words_per_minute, self.max_segment_words,
                             paper_title=paper.title, abstract=paper.abstract)

    def write(self, paper: Paper, outline: list[OutlineItem], speakers: list[Speaker], minutes: float, *,
              on_segment: Callable[[int, int], None] | None = None,
              check_cancel: Callable[[], None] | None = None) -> tuple[Script, list[SegmentReport]]:
        plans = self.plan(paper, outline, minutes)
        turns: list[Turn] = []
        reports: list[SegmentReport] = []
        for plan in plans:
            if check_cancel:
                check_cancel()
            segment_turns, report = self.write_segment(plan, len(plans), paper, speakers, turns[-3:])
            turns.extend(segment_turns)
            reports.append(report)
            if on_segment:
                on_segment(plan.index + 1, len(plans))
        script = Script(title=paper.title, speakers=list(speakers), turns=turns,
                        segment_titles=[p.title for p in plans])
        return script, reports

    def write_segment(self, plan: SegmentPlan, count: int, paper: Paper, speakers: list[Speaker],
                      previous: list[Turn]) -> tuple[list[Turn], SegmentReport]:
        target = plan.target_words
        low = math.floor(target * (1 - self.tolerance))
        high = math.ceil(target * (1 + self.tolerance))
        system = render("segment_system")
        previous_text = "\n".join(f"{t.speaker}: {truncate_words(t.text, 80)}" for t in previous) or "(none)"

        best: list[Turn] | None = None
        best_error = math.inf
        feedback = ""
        attempts = truncated = invalid = 0
        max_tokens = plan.max_tokens
        for _ in range(1 + self.max_regenerations):
            attempts += 1
            user = render(
                "segment_user", paper_title=paper.title, speakers=speakers_line(speakers),
                index=plan.index + 1, count=count, segment_title=plan.title, kind=plan.kind,
                target_words=target, low=low, high=high, position_note=POSITION_NOTES[plan.kind],
                notes=plan.notes, previous=previous_text, feedback=f"\n{feedback}\n" if feedback else "",
            )
            result = self.llm.complete_json(task="write_segment", system=system, user=user,
                                            schema=SEGMENT_SCHEMA, max_tokens=max_tokens)
            if result.truncated:
                truncated += 1
                max_tokens = min(MODEL_OUTPUT_LIMIT, int(max_tokens * 1.5))
                feedback = ("Your previous answer was cut off before the JSON was complete. Write the "
                            f"whole segment in about {target} words and close the JSON.")
                continue
            try:
                turns = parse_turns(result.data, speakers, plan.index)
            except ScriptFormatError as exc:
                invalid += 1
                feedback = (f"Your previous answer was invalid: {exc}. Use only these speaker names: "
                            f"{', '.join(s.name for s in speakers)}.")
                continue
            words = sum(t.words for t in turns)
            if abs(words - target) < best_error:
                best, best_error = turns, abs(words - target)
            if low <= words <= high:
                break
            direction = ("longer: add explanation, examples and follow-up questions grounded in the notes"
                         if words < low else "shorter: cut repetition and side remarks")
            feedback = (f"Your previous draft had {words} words but this segment needs about {target} "
                        f"(between {low} and {high}). Rewrite it {direction}.")
            log.info("segment %d: %d words vs target %d, regenerating", plan.index, words, target)

        if best is None:
            raise ScriptFormatError(f"segment '{plan.title}' failed after {attempts} attempts "
                                    f"({truncated} truncated, {invalid} invalid)")
        trimmed = False
        if sum(t.words for t in best) > high:
            best, trimmed = trim_turns(best, high), True
        actual = sum(t.words for t in best)
        report = SegmentReport(plan.index, plan.title, target, actual, attempts, truncated, invalid,
                               low <= actual <= high, trimmed)
        return best, report
