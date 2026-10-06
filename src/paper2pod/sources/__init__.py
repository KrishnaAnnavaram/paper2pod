"""Where papers come from: the arXiv API, or a bundled sample for offline demos."""
from .arxiv import ArxivClient, find_arxiv_id, normalize_arxiv_id, parse_atom_feed
from .base import PaperSource
from .local import LocalPaperSource

__all__ = ["ArxivClient", "LocalPaperSource", "PaperSource", "find_arxiv_id", "normalize_arxiv_id",
           "parse_atom_feed"]
