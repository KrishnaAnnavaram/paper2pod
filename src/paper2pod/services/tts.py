"""Text-to-speech interface and the OpenAI adapter.

Every engine returns raw 16-bit little-endian mono PCM at ``engine.sample_rate``. Keeping one
uncompressed format end to end means mixing and duration measurement need no FFmpeg.
"""
from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from ..errors import MissingDependency, TransientError
from ..retry import with_retries

log = logging.getLogger(__name__)


@runtime_checkable
class TTSEngine(Protocol):
    name: str
    sample_rate: int
    max_chars: int

    def synthesize(self, text: str, voice: str) -> bytes:
        """Return PCM16 mono audio for ``text`` (at most ``max_chars`` characters)."""
        ...


class OpenAITTS:
    """OpenAI speech endpoint, requested as raw PCM (24 kHz, 16-bit, mono)."""

    sample_rate = 24_000
    max_chars = 4_000  # the endpoint accepts up to 4096 characters per request

    def __init__(self, api_key: str, model: str = "tts-1", base_url: str | None = None,
                 max_retries: int = 3, timeout: float = 120.0):
        try:
            import openai
        except ImportError as exc:
            raise MissingDependency("openai", "openai") from exc
        self._openai = openai
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url, max_retries=0, timeout=timeout)
        self.model, self.max_retries = model, max_retries
        self.name = f"openai:{model}"

    def synthesize(self, text: str, voice: str) -> bytes:
        if len(text) > self.max_chars:
            raise ValueError(f"TTS input is {len(text)} characters; chunk it to {self.max_chars} first")
        transient = (self._openai.RateLimitError, self._openai.APIConnectionError,
                     self._openai.APITimeoutError, self._openai.InternalServerError)

        def call() -> bytes:
            try:
                response = self._client.audio.speech.create(
                    model=self.model, voice=voice, input=text, response_format="pcm")
                return response.content
            except transient as exc:
                raise TransientError(f"OpenAI TTS {type(exc).__name__}") from exc

        return with_retries(call, attempts=self.max_retries, label="TTS")
