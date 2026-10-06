"""Explicit voice catalog and a deterministic speaker -> voice assignment.

The style labels describe how each OpenAI preset voice is commonly perceived. They are an
approximation, which is why every assignment can be overridden (``PAPER2POD_VOICES`` or a
speaker's ``voice`` field). Two speakers never share a voice.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models import Speaker


@dataclass(frozen=True)
class Voice:
    name: str
    style: str  # "male" | "female" | "neutral"


OPENAI_VOICES: tuple[Voice, ...] = (
    Voice("onyx", "male"),
    Voice("echo", "male"),
    Voice("nova", "female"),
    Voice("shimmer", "female"),
    Voice("alloy", "neutral"),
    Voice("fable", "neutral"),
)


def assign_voices(speakers: list[Speaker], catalog: tuple[Voice, ...] = OPENAI_VOICES,
                  overrides: dict[str, str] | None = None) -> dict[str, str]:
    """Return ``{speaker name: voice name}`` with distinct voices.

    Priority: explicit overrides, then a speaker's own ``voice``, then the first unused voice
    whose style matches the speaker's ``voice_style``, then a neutral voice, then any free voice.
    """
    if len(speakers) > len(catalog):
        raise ValueError(f"{len(speakers)} speakers but only {len(catalog)} distinct voices are available")
    known = {v.name: v for v in catalog}
    overrides = {k.lower(): v.lower() for k, v in (overrides or {}).items()}
    assigned: dict[str, str] = {}
    used: set[str] = set()

    def take(speaker: Speaker, voice: str) -> None:
        if voice not in known:
            raise ValueError(f"unknown voice {voice!r} for {speaker.name}; choose from {sorted(known)}")
        if voice in used:
            raise ValueError(f"voice {voice!r} is assigned to more than one speaker")
        assigned[speaker.name] = voice
        used.add(voice)

    for speaker in speakers:  # pinned voices first, so automatic choices never steal them
        pinned = overrides.get(speaker.name.lower()) or speaker.voice
        if pinned:
            take(speaker, pinned.lower())

    for speaker in speakers:
        if speaker.name in assigned:
            continue
        free = [v for v in catalog if v.name not in used]
        preference = [speaker.voice_style] if speaker.voice_style in ("male", "female", "neutral") else []
        preference += ["neutral"] if "neutral" not in preference else []
        choice = next((v for style in preference for v in free if v.style == style), free[0])
        take(speaker, choice.name)
    return assigned
