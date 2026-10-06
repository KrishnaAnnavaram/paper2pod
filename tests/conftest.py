from __future__ import annotations

from typing import Any

import pytest

from paper2pod.config import Settings
from paper2pod.models import Paper, Speaker
from paper2pod.services.llm import LLMResult


class ScriptedLLM:
    """Returns pre-programmed responses in order and records every call."""

    name = "scripted"

    def __init__(self, responses: list[LLMResult]):
        self.responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, **kwargs) -> LLMResult:
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("ScriptedLLM ran out of responses")
        return self.responses.pop(0)


def turns_payload(*pairs: tuple[str, str]) -> dict[str, Any]:
    return {"turns": [{"speaker": s, "text": t, "direction": None} for s, t in pairs]}


def words(n: int, word: str = "word") -> str:
    return " ".join([word] * n) + "."


@pytest.fixture
def speakers() -> list[Speaker]:
    return [Speaker("Alex", "host", "female"), Speaker("Sam", "expert", "male")]


@pytest.fixture
def paper() -> Paper:
    return Paper(arxiv_id="demo", title="A Toy Paper", authors=["A. Example"], abstract="We study toys.")


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(backend="fake", data_dir=tmp_path / "data", pause_ms=50)
