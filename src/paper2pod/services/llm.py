"""Chat-model interface with structured (JSON-schema) output, plus the OpenAI adapter."""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from ..errors import MissingDependency, ScriptFormatError, TransientError
from ..retry import with_retries

log = logging.getLogger(__name__)


@dataclass
class LLMResult:
    data: dict[str, Any]
    finish_reason: str = "stop"  # "length" means the model hit max_tokens and the output is incomplete
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def truncated(self) -> bool:
        return self.finish_reason == "length"


@runtime_checkable
class LLM(Protocol):
    name: str

    def complete_json(self, *, task: str, system: str, user: str, schema: dict[str, Any],
                      max_tokens: int) -> LLMResult:
        """Return an object that follows ``schema``. ``task`` is a short label used for logging."""
        ...


@dataclass
class UsageMeter:
    """Thread-safe token counter, reported per task in metrics.json (never logs content)."""

    calls: dict[str, int] = field(default_factory=dict)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, task: str, result: LLMResult) -> None:
        with self._lock:
            self.calls[task] = self.calls.get(task, 0) + 1
            self.prompt_tokens += result.prompt_tokens
            self.completion_tokens += result.completion_tokens

    def to_dict(self) -> dict[str, Any]:
        return {"calls": dict(self.calls), "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens}


class MeteredLLM:
    """Wraps any LLM and records token usage."""

    def __init__(self, inner: LLM, meter: UsageMeter):
        self.inner, self.meter = inner, meter
        self.name = inner.name

    def complete_json(self, **kwargs) -> LLMResult:
        result = self.inner.complete_json(**kwargs)
        self.meter.record(kwargs.get("task", "unknown"), result)
        return result


class OpenAILLM:
    """OpenAI Chat Completions with strict JSON-schema structured outputs."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini", base_url: str | None = None,
                 temperature: float = 0.7, max_retries: int = 3, timeout: float = 120.0):
        try:
            import openai
        except ImportError as exc:
            raise MissingDependency("openai", "openai") from exc
        self._openai = openai
        # The SDK's own retries are disabled so that one retry policy (ours) applies everywhere.
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url, max_retries=0, timeout=timeout)
        self.model, self.temperature, self.max_retries = model, temperature, max_retries
        self.name = f"openai:{model}"

    def complete_json(self, *, task: str, system: str, user: str, schema: dict[str, Any],
                      max_tokens: int) -> LLMResult:
        transient = (self._openai.RateLimitError, self._openai.APIConnectionError,
                     self._openai.APITimeoutError, self._openai.InternalServerError)

        def call():
            try:
                return self._client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    response_format={"type": "json_schema",
                                     "json_schema": {"name": task, "schema": schema, "strict": True}},
                    max_completion_tokens=max_tokens,
                    temperature=self.temperature,
                )
            except transient as exc:
                raise TransientError(f"OpenAI {type(exc).__name__}") from exc

        response = with_retries(call, attempts=self.max_retries, label=f"LLM {task}")
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        result = LLMResult(
            data={},
            finish_reason=choice.finish_reason or "stop",
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )
        log.info("LLM %s: %d prompt + %d completion tokens (finish=%s)", task, result.prompt_tokens,
                 result.completion_tokens, result.finish_reason)
        content = choice.message.content or ""
        try:
            result.data = json.loads(content) if content else {}
        except json.JSONDecodeError as exc:
            if result.truncated:
                return result  # the caller sees truncated=True and asks for a shorter answer
            raise ScriptFormatError(f"model returned invalid JSON for {task}") from exc
        return result
