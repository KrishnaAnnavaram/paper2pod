"""Versioned prompt templates stored as package data (``paper2pod/prompts/*.txt``)."""
from __future__ import annotations

from functools import lru_cache
from importlib import resources
from string import Template


@lru_cache(maxsize=None)
def load_prompt(name: str) -> Template:
    text = resources.files("paper2pod").joinpath("prompts", f"{name}.txt").read_text(encoding="utf-8")
    return Template(text)


def render(name: str, **values) -> str:
    return load_prompt(name).substitute(**{k: str(v) for k, v in values.items()})
