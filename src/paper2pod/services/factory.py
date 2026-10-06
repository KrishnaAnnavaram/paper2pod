"""Build service adapters from ``Settings``."""
from __future__ import annotations

from ..config import Settings
from ..sources import ArxivClient, LocalPaperSource, PaperSource
from .fakes import FakeLLM, FakeTTS
from .llm import LLM, OpenAILLM
from .tts import OpenAITTS, TTSEngine


def build_llm(settings: Settings) -> LLM:
    if settings.backend == "fake":
        return FakeLLM()
    return OpenAILLM(settings.require_openai_key(), model=settings.llm_model,
                     base_url=settings.openai_base_url, max_retries=settings.max_retries)


def build_tts(settings: Settings) -> TTSEngine:
    if settings.backend == "fake":
        return FakeTTS(words_per_minute=settings.words_per_minute)
    return OpenAITTS(settings.require_openai_key(), model=settings.tts_model,
                     base_url=settings.openai_base_url, max_retries=settings.max_retries)


def build_source(settings: Settings, offline: bool = False) -> PaperSource:
    if offline:
        return LocalPaperSource()
    return ArxivClient(settings.cache_dir, max_retries=settings.max_retries)
