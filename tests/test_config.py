"""Problem 9: hard-wired private model, hand-parsed .env that crashed when missing."""
from pathlib import Path

import pytest

from paper2pod.config import Settings, load_dotenv_if_present, parse_voice_overrides
from paper2pod.errors import ConfigError
from paper2pod.services.factory import build_llm, build_tts
from paper2pod.services.fakes import FakeLLM, FakeTTS


def test_defaults_use_a_public_model():
    s = Settings.from_env({})
    assert s.llm_model == "gpt-4o-mini" and s.backend == "openai"
    assert s.openai_api_key is None and s.jobs_dir == Path("data") / "jobs"


def test_values_come_from_env():
    s = Settings.from_env({"PAPER2POD_BACKEND": "FAKE", "PAPER2POD_LLM_MODEL": "my-model",
                           "PAPER2POD_WORDS_PER_MINUTE": "140", "PAPER2POD_VOICES": "Alex:Nova, Sam:onyx",
                           "OPENAI_API_KEY": "placeholder"})
    assert s.backend == "fake" and s.llm_model == "my-model" and s.words_per_minute == 140
    assert s.voice_overrides == {"Alex": "nova", "Sam": "onyx"}
    assert "placeholder" not in repr(s)  # the key is never printed


@pytest.mark.parametrize("env", [
    {"PAPER2POD_BACKEND": "gpt"},
    {"PAPER2POD_WORDS_PER_MINUTE": "fast"},
    {"PAPER2POD_LENGTH_TOLERANCE": "0.9"},
])
def test_invalid_values_raise_config_error(env):
    with pytest.raises(ConfigError):
        Settings.from_env(env)


def test_bad_voice_override():
    with pytest.raises(ConfigError):
        parse_voice_overrides("Alex")


def test_missing_dotenv_is_not_an_error(tmp_path):
    assert load_dotenv_if_present(tmp_path / "nope.env") is False


def test_openai_backend_without_key_gives_a_clear_error():
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        build_llm(Settings(backend="openai"))


def test_fake_backend_needs_no_key():
    s = Settings(backend="fake")
    assert isinstance(build_llm(s), FakeLLM) and isinstance(build_tts(s), FakeTTS)
