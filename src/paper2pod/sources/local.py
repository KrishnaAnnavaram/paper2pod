"""Offline paper source backed by a text file (the bundled synthetic sample by default)."""
from __future__ import annotations

from importlib import resources
from pathlib import Path

from ..models import Paper
from ..parsing.sections import split_sections

SAMPLE_ID = "demo"


def sample_paper_text() -> str:
    return resources.files("paper2pod").joinpath("demo", "sample_paper.txt").read_text(encoding="utf-8")


class LocalPaperSource:
    """Serves one paper from local text. Used by ``paper2pod demo`` and by the tests."""

    def __init__(self, text: str | None = None, paper_id: str = SAMPLE_ID):
        self.text = text if text is not None else sample_paper_text()
        self.paper_id = paper_id
        lines = [line.strip() for line in self.text.splitlines() if line.strip()]
        self._title = lines[0] if lines else "Untitled"
        self._authors = [a.strip() for a in lines[1].split(",")] if len(lines) > 1 else []
        abstract = next((s.text for s in split_sections(self.text) if s.title.lower() == "abstract"), "")
        self._abstract = " ".join(abstract.split())

    def _paper(self) -> Paper:
        return Paper(arxiv_id=self.paper_id, title=self._title, authors=self._authors,
                     abstract=self._abstract, published="")

    def search(self, query: str, max_results: int = 5) -> list[Paper]:
        return [self._paper()] if max_results > 0 else []

    def resolve(self, ref: str) -> Paper:
        return self._paper()

    def fetch_fulltext(self, paper: Paper, workdir: Path) -> str:
        Path(workdir).mkdir(parents=True, exist_ok=True)
        return self.text
