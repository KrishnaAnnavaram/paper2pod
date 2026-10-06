"""Wire settings, adapters, pipeline and job runner together."""
from __future__ import annotations

import logging

from .config import Settings
from .jobs import JobRunner, JobStore
from .pipeline import Pipeline
from .services.factory import build_llm, build_source, build_tts


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def build_pipeline(settings: Settings, offline: bool = False) -> Pipeline:
    """``offline=True`` uses the bundled sample paper and the fake LLM/TTS (no network, no keys)."""
    if offline:
        settings = settings.with_overrides(backend="fake")
    return Pipeline(settings, build_source(settings, offline), build_llm(settings), build_tts(settings))


def build_runner(settings: Settings, offline: bool = False) -> JobRunner:
    pipeline = build_pipeline(settings, offline)
    return JobRunner(JobStore(settings.jobs_dir), pipeline.run, max_workers=settings.max_workers)
