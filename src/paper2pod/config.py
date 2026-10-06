"""Runtime configuration, read from environment variables.

A ``.env`` file is loaded only when it exists and python-dotenv is installed; a missing file is
never an error. Secrets are only ever read from the environment and are never logged.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping

from .errors import ConfigError

BACKENDS = ("openai", "fake")


def load_dotenv_if_present(path: str | os.PathLike = ".env") -> bool:
    """Load ``path`` into ``os.environ`` without overriding variables that are already set."""
    env_file = Path(path)
    if not env_file.is_file():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False
    load_dotenv(env_file, override=False)
    return True


def parse_voice_overrides(raw: str | None) -> dict[str, str]:
    """Parse ``"Alex:nova, Sam:onyx"`` into ``{"Alex": "nova", "Sam": "onyx"}``."""
    overrides: dict[str, str] = {}
    if not raw:
        return overrides
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        name, sep, voice = item.partition(":")
        if not sep or not name.strip() or not voice.strip():
            raise ConfigError(f"PAPER2POD_VOICES entry {item!r} must look like 'Speaker:voice'")
        overrides[name.strip()] = voice.strip().lower()
    return overrides


def _number(env: Mapping[str, str], key: str, default, cast, low=None, high=None):
    raw = env.get(key, "").strip()
    if not raw:
        return default
    try:
        value = cast(raw)
    except ValueError as exc:
        raise ConfigError(f"{key}={raw!r} is not a valid {cast.__name__}") from exc
    if (low is not None and value < low) or (high is not None and value > high):
        raise ConfigError(f"{key}={value} must be between {low} and {high}")
    return value


@dataclass(frozen=True)
class Settings:
    backend: str = "openai"
    openai_api_key: str | None = field(default=None, repr=False)
    openai_base_url: str | None = None
    llm_model: str = "gpt-4o-mini"
    tts_model: str = "tts-1"
    words_per_minute: int = 150
    length_tolerance: float = 0.12
    max_segment_words: int = 650
    max_regenerations: int = 2
    max_retries: int = 3
    data_dir: Path = Path("data")
    voice_overrides: dict[str, str] = field(default_factory=dict)
    pause_ms: int = 300
    max_workers: int = 2
    log_level: str = "INFO"

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env
        backend = env.get("PAPER2POD_BACKEND", "").strip().lower() or "openai"
        if backend not in BACKENDS:
            raise ConfigError(f"PAPER2POD_BACKEND must be one of {BACKENDS}, got {backend!r}")
        return cls(
            backend=backend,
            openai_api_key=env.get("OPENAI_API_KEY", "").strip() or None,
            openai_base_url=env.get("OPENAI_BASE_URL", "").strip() or None,
            llm_model=env.get("PAPER2POD_LLM_MODEL", "").strip() or cls.llm_model,
            tts_model=env.get("PAPER2POD_TTS_MODEL", "").strip() or cls.tts_model,
            words_per_minute=_number(env, "PAPER2POD_WORDS_PER_MINUTE", cls.words_per_minute, int, 80, 250),
            length_tolerance=_number(env, "PAPER2POD_LENGTH_TOLERANCE", cls.length_tolerance, float, 0.02, 0.5),
            max_segment_words=_number(env, "PAPER2POD_MAX_SEGMENT_WORDS", cls.max_segment_words, int, 150, 1500),
            max_regenerations=_number(env, "PAPER2POD_MAX_REGENERATIONS", cls.max_regenerations, int, 0, 5),
            max_retries=_number(env, "PAPER2POD_MAX_RETRIES", cls.max_retries, int, 1, 10),
            data_dir=Path(env.get("PAPER2POD_DATA_DIR", "").strip() or "data"),
            voice_overrides=parse_voice_overrides(env.get("PAPER2POD_VOICES")),
            pause_ms=_number(env, "PAPER2POD_PAUSE_MS", cls.pause_ms, int, 0, 3000),
            max_workers=_number(env, "PAPER2POD_MAX_WORKERS", cls.max_workers, int, 1, 16),
            log_level=env.get("PAPER2POD_LOG_LEVEL", "").strip().upper() or "INFO",
        )

    def with_overrides(self, **changes) -> "Settings":
        return replace(self, **changes)

    def require_openai_key(self) -> str:
        if not self.openai_api_key:
            raise ConfigError(
                "OPENAI_API_KEY is not set. Put it in your environment or .env file, "
                "or use the offline backend (PAPER2POD_BACKEND=fake / `paper2pod demo`)."
            )
        return self.openai_api_key
