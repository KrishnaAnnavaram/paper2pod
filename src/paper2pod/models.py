"""Plain data objects passed between pipeline stages. All of them round-trip through JSON."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .text_utils import count_words

ROLES = ("host", "expert", "guest")
VOICE_STYLES = ("male", "female", "neutral", "any")


@dataclass
class Paper:
    arxiv_id: str
    title: str
    authors: list[str] = field(default_factory=list)
    abstract: str = ""
    pdf_url: str = ""
    published: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Paper":
        return cls(**{k: data[k] for k in cls.__dataclass_fields__ if k in data})


@dataclass
class Section:
    title: str
    text: str

    @property
    def words(self) -> int:
        return count_words(self.text)


@dataclass
class Speaker:
    name: str
    role: str = "guest"
    voice_style: str = "any"
    voice: str | None = None

    def __post_init__(self):
        self.name = self.name.strip()
        self.role = self.role.strip().lower() or "guest"
        self.voice_style = self.voice_style.strip().lower() or "any"
        if not self.name:
            raise ValueError("speaker name must not be empty")
        if self.role not in ROLES:
            raise ValueError(f"speaker role must be one of {ROLES}, got {self.role!r}")
        if self.voice_style not in VOICE_STYLES:
            raise ValueError(f"voice_style must be one of {VOICE_STYLES}, got {self.voice_style!r}")

    @classmethod
    def parse(cls, spec: str) -> "Speaker":
        """Parse ``"Name[:role[:style[:voice]]]"``, e.g. ``"Alex:host:female"``."""
        parts = [p.strip() for p in spec.split(":")]
        name = parts[0]
        role = parts[1] if len(parts) > 1 and parts[1] else "guest"
        style = parts[2] if len(parts) > 2 and parts[2] else "any"
        voice = parts[3].lower() if len(parts) > 3 and parts[3] else None
        return cls(name=name, role=role, voice_style=style, voice=voice)


def default_speakers() -> list[Speaker]:
    return [Speaker("Alex", "host", "female"), Speaker("Sam", "expert", "male")]


@dataclass
class Turn:
    speaker: str
    text: str
    direction: str | None = None  # delivery hint such as "laughs"; kept apart and never spoken
    segment: int = 0

    @property
    def words(self) -> int:
        return count_words(self.text)


@dataclass
class Script:
    title: str
    speakers: list[Speaker]
    turns: list[Turn]
    segment_titles: list[str] = field(default_factory=list)

    @property
    def words(self) -> int:
        return sum(t.words for t in self.turns)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Script":
        return cls(
            title=data["title"],
            speakers=[Speaker(**s) for s in data["speakers"]],
            turns=[Turn(**t) for t in data["turns"]],
            segment_titles=list(data.get("segment_titles", [])),
        )


@dataclass
class PodcastRequest:
    paper: str
    minutes: int = 10
    speakers: list[Speaker] = field(default_factory=default_speakers)
    export_mp3: bool = False

    def validate(self) -> "PodcastRequest":
        if not self.paper or not self.paper.strip():
            raise ValueError("a paper reference (arXiv ID or URL) is required")
        if not 2 <= self.minutes <= 60:
            raise ValueError("minutes must be between 2 and 60")
        if not 2 <= len(self.speakers) <= 4:
            raise ValueError("a podcast needs between 2 and 4 speakers")
        names = [s.name.lower() for s in self.speakers]
        if len(set(names)) != len(names):
            raise ValueError("speaker names must be unique")
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PodcastRequest":
        speakers = [s if isinstance(s, Speaker) else Speaker(**s) for s in data.get("speakers") or []]
        return cls(
            paper=str(data.get("paper", "")),
            minutes=int(data.get("minutes", 10)),
            speakers=speakers or default_speakers(),
            export_mp3=bool(data.get("export_mp3", False)),
        ).validate()
