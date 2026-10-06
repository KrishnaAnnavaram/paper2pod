"""The interface every paper source implements."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from ..models import Paper


@runtime_checkable
class PaperSource(Protocol):
    def search(self, query: str, max_results: int = 5) -> list[Paper]:
        """Free-text search. A query that contains an arXiv ID resolves that paper directly."""
        ...

    def resolve(self, ref: str) -> Paper:
        """Turn an arXiv ID or URL into paper metadata."""
        ...

    def fetch_fulltext(self, paper: Paper, workdir: Path) -> str:
        """Return the raw full text of ``paper`` (downloading it into ``workdir`` if needed)."""
        ...
