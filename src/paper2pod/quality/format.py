"""Structural checks on a finished script."""
from __future__ import annotations

import re

from ..models import Script

MAX_TURN_WORDS = 180
MAX_SAME_SPEAKER_RUN = 2
_MARKUP = re.compile(r"\*\*|__|^#{1,6}\s|\[[a-z ]+\]", re.M)


def check_format(script: Script) -> list[str]:
    """Return human-readable issues (an empty list means the script looks well formed)."""
    issues: list[str] = []
    names = {s.name for s in script.speakers}
    if not script.turns:
        return ["script has no turns"]
    spoken = {t.speaker for t in script.turns}
    for name in sorted(names - spoken):
        issues.append(f"speaker {name} never speaks")
    run_speaker, run_length = None, 0
    for i, turn in enumerate(script.turns):
        if turn.speaker not in names:
            issues.append(f"turn {i}: unknown speaker {turn.speaker!r}")
        if not turn.text.strip():
            issues.append(f"turn {i}: empty text")
        if turn.words > MAX_TURN_WORDS:
            issues.append(f"turn {i}: monologue of {turn.words} words (limit {MAX_TURN_WORDS})")
        if _MARKUP.search(turn.text):
            issues.append(f"turn {i}: markup left in spoken text")
        for name in names:
            if turn.text.lower().startswith(name.lower() + ":"):
                issues.append(f"turn {i}: speaker label inside text")
        run_length = run_length + 1 if turn.speaker == run_speaker else 1
        run_speaker = turn.speaker
        if run_length == MAX_SAME_SPEAKER_RUN + 1:
            issues.append(f"turn {i}: {turn.speaker} speaks more than {MAX_SAME_SPEAKER_RUN} turns in a row")
    return issues
