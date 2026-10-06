"""A small conversational front-end on top of the job runner.

Each ``ChatSession`` owns its own bounded history and its own job list. There is no module-level
memory, history is stored once as structured messages (never re-pasted into the user's text), and
the session only *calls* the pipeline through the runner: it never runs work inline.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .jobs import JobRunner, JobStatus
from .models import Paper, PodcastRequest, Speaker, default_speakers
from .sources.arxiv import find_arxiv_id
from .sources.base import PaperSource

ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": -1}
_MINUTES = re.compile(r"\b(\d{1,2})\s*-?\s*min(?:ute)?s?\b", re.I)
_CHOICE = re.compile(r"(?:#|\bnumber\s+|\bno\.?\s*|\boption\s+)(\d)\b|\b(first|second|third|fourth|fifth|last)\b",
                     re.I)
_PODCAST = re.compile(r"\b(podcast|episode|make|create|generate|produce|turn)\b", re.I)
_SEARCH_FILLER = re.compile(
    r"^(?:please\s+)?(?:can you\s+)?(?:find|search(?:\s+for)?|look\s+up|show\s+me|get)\s+(?:me\s+)?"
    r"(?:the\s+)?(?:papers?|articles?)?\s*(?:about|on|called|titled)?\s*", re.I)


@dataclass
class ChatMessage:
    role: str
    content: str


class ConversationMemory:
    """Bounded, per-session message history (by message count and by total characters)."""

    def __init__(self, max_messages: int = 12, max_chars: int = 6000):
        self.max_messages, self.max_chars = max_messages, max_chars
        self._messages: list[ChatMessage] = []

    def add(self, role: str, content: str) -> None:
        self._messages.append(ChatMessage(role, content))
        while len(self._messages) > self.max_messages:
            self._messages.pop(0)
        while len(self._messages) > 1 and sum(len(m.content) for m in self._messages) > self.max_chars:
            self._messages.pop(0)

    def messages(self) -> list[dict[str, str]]:
        """Structured history, oldest first, ready to pass as chat messages to any LLM."""
        return [{"role": m.role, "content": m.content} for m in self._messages]

    def __len__(self) -> int:
        return len(self._messages)


@dataclass
class Intent:
    kind: str  # "make" | "search" | "status" | "cancel" | "help"
    paper_ref: str | None = None
    query: str = ""
    minutes: int | None = None
    choice: int | None = None


def parse_intent(text: str) -> Intent:
    raw = (text or "").strip()
    low = raw.lower()
    minutes_match = _MINUTES.search(raw)
    minutes = int(minutes_match.group(1)) if minutes_match else None
    if not raw or low in {"help", "?", "hi", "hello"}:
        return Intent("help")
    if re.search(r"\b(status|progress|done yet|how far|ready)\b", low):
        return Intent("status")
    if re.search(r"\b(cancel|stop|abort)\b", low):
        return Intent("cancel")
    arxiv_id = find_arxiv_id(raw)
    wants_podcast = bool(_PODCAST.search(raw)) or minutes is not None
    if arxiv_id:
        return Intent("make" if wants_podcast else "search", paper_ref=arxiv_id, query=arxiv_id, minutes=minutes)
    choice_match = _CHOICE.search(raw)
    if choice_match and wants_podcast:
        choice = int(choice_match.group(1)) if choice_match.group(1) else ORDINALS[choice_match.group(2).lower()]
        return Intent("make", choice=choice, minutes=minutes)
    query = _MINUTES.sub(" ", raw)
    query = re.sub(r"\b(?:and\s+)?(?:make|create|generate|produce|turn)\b.*$", " ", query, flags=re.I)
    query = _SEARCH_FILLER.sub("", query.strip()).strip(" .?!\"'")
    return Intent("search", query=query, minutes=minutes)


@dataclass
class ChatSession:
    runner: JobRunner
    source: PaperSource
    default_minutes: int = 10
    speakers: list[Speaker] = field(default_factory=default_speakers)
    memory: ConversationMemory = field(default_factory=ConversationMemory)
    last_results: list[Paper] = field(default_factory=list)
    job_ids: list[str] = field(default_factory=list)

    def send(self, text: str) -> str:
        self.memory.add("user", text)
        try:
            reply = self._handle(parse_intent(text))
        except Exception as exc:  # noqa: BLE001 - a chat turn must always answer
            reply = f"Sorry, that failed: {exc}"
        self.memory.add("assistant", reply)
        return reply

    # -- handlers ------------------------------------------------------------------------------------
    def _handle(self, intent: Intent) -> str:
        if intent.kind == "help":
            return ("Ask me to find a paper (\"find papers on graph transformers\"), then say \"make a "
                    "10 minute podcast of the first one\", or give an arXiv ID directly "
                    "(\"podcast 1706.03762, 15 minutes\"). Ask \"status\" any time.")
        if intent.kind == "status":
            return self._status()
        if intent.kind == "cancel":
            return self._cancel()
        if intent.kind == "search":
            return self._search(intent)
        return self._make(intent)

    def _search(self, intent: Intent) -> str:
        if not intent.query:
            return "What should I search for?"
        self.last_results = self.source.search(intent.query, max_results=5)
        if not self.last_results:
            return f"No papers found for \"{intent.query}\"."
        lines = [f"{i}. {p.title} ({p.arxiv_id})" for i, p in enumerate(self.last_results, start=1)]
        return "Here is what I found:\n" + "\n".join(lines) + "\nSay e.g. \"make a podcast of #1\"."

    def _make(self, intent: Intent) -> str:
        ref = intent.paper_ref
        if ref is None:
            if not self.last_results:
                return "Search for a paper first, or give me an arXiv ID."
            index = intent.choice - 1 if intent.choice and intent.choice > 0 else len(self.last_results) - 1
            if not 0 <= index < len(self.last_results):
                return f"Pick a number between 1 and {len(self.last_results)}."
            ref = self.last_results[index].arxiv_id
        minutes = intent.minutes or self.default_minutes
        job = self.runner.submit(PodcastRequest(paper=ref, minutes=minutes, speakers=list(self.speakers)))
        self.job_ids.append(job.id)
        return f"Started a {minutes}-minute podcast for {ref} (job {job.id[:8]}). Ask \"status\" to follow it."

    def _status(self) -> str:
        if not self.job_ids:
            return "You have no podcast jobs yet."
        job = self.runner.store.get(self.job_ids[-1])
        if job.status == JobStatus.SUCCEEDED:
            return f"Your podcast is ready: {job.outputs.get('audio')}"
        if job.status == JobStatus.FAILED:
            return f"The job failed: {job.error}"
        return f"Job {job.id[:8]} is {job.status.value}: {job.stage} ({job.progress}%) {job.message}".strip()

    def _cancel(self) -> str:
        if not self.job_ids:
            return "There is nothing to cancel."
        job = self.runner.cancel(self.job_ids[-1])
        return f"Cancellation requested for job {job.id[:8]} (status: {job.status.value})."
