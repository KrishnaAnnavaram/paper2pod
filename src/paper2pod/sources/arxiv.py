"""arXiv API client: ID handling, search, metadata and PDF download, with an on-disk cache.

Only the standard library is used. HTTP access goes through an injectable ``http_get`` callable so
tests run without the network.
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Callable

from ..errors import PaperNotFound, TransientError
from ..models import Paper
from ..parsing.pdf import extract_pdf_text
from ..retry import with_retries

log = logging.getLogger(__name__)

API_URL = "https://export.arxiv.org/api/query"
USER_AGENT = "paper2pod/0.1 (+https://github.com/KrishnaAnnavaram/paper2pod)"
ATOM = "{http://www.w3.org/2005/Atom}"

# 2007+ identifiers (1706.03762, 2401.01234v2) and pre-2007 ones (hep-th/9901001, math.GT/0309136)
_NEW_STYLE = re.compile(r"(?<![\w.])(\d{4}\.\d{4,5})(?:v\d+)?(?!\w|\.\d)")
_OLD_STYLE = re.compile(r"(?<![\w.\-])([a-z][a-z\-]*(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?(?!\w|\.\d)")

HttpGet = Callable[[str], bytes]


def find_arxiv_id(text: str) -> str | None:
    """Return the first arXiv identifier (without version) found anywhere in ``text``."""
    if not text:
        return None
    for pattern in (_NEW_STYLE, _OLD_STYLE):
        match = pattern.search(text)
        if match:
            return match.group(1)
    return None


def normalize_arxiv_id(ref: str) -> str:
    """Accept a bare ID, a versioned ID, or an abs/pdf URL and return the bare ID."""
    found = find_arxiv_id((ref or "").strip())
    if not found:
        raise PaperNotFound(f"not an arXiv identifier or URL: {ref!r}")
    return found


def _is_mostly_id(query: str, arxiv_id: str) -> bool:
    leftover = query.replace(arxiv_id, " ")
    leftover = re.sub(r"https?://\S+|arxiv(?:\.org)?|abs|pdf|v\d+|[^\w]+", " ", leftover, flags=re.I)
    return len(leftover.split()) <= 6


def _text(node: ET.Element | None) -> str:
    return " ".join((node.text or "").split()) if node is not None else ""


def parse_atom_feed(xml_bytes: bytes) -> list[Paper]:
    """Parse an arXiv Atom response into ``Paper`` objects (error entries are skipped)."""
    root = ET.fromstring(xml_bytes)
    papers: list[Paper] = []
    for entry in root.findall(f"{ATOM}entry"):
        entry_id = _text(entry.find(f"{ATOM}id"))
        if "/api/errors" in entry_id:
            continue
        arxiv_id = find_arxiv_id(entry_id)
        if not arxiv_id:
            continue
        pdf_url = ""
        for link in entry.findall(f"{ATOM}link"):
            if link.get("title") == "pdf" or link.get("type") == "application/pdf":
                pdf_url = link.get("href", "")
        papers.append(Paper(
            arxiv_id=arxiv_id,
            title=_text(entry.find(f"{ATOM}title")),
            authors=[_text(a.find(f"{ATOM}name")) for a in entry.findall(f"{ATOM}author")],
            abstract=_text(entry.find(f"{ATOM}summary")),
            pdf_url=pdf_url or f"https://arxiv.org/pdf/{arxiv_id}",
            published=_text(entry.find(f"{ATOM}published"))[:10],
        ))
    return papers


def urllib_get(url: str, timeout: float = 60.0) -> bytes:
    """Default HTTP GET. Rate limits, timeouts and server errors become ``TransientError``."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (https only)
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 429 or exc.code >= 500:
            raise TransientError(f"arXiv returned HTTP {exc.code}") from exc
        if exc.code == 404:
            raise PaperNotFound(f"not found: {url}") from exc
        raise
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise TransientError(f"network error: {exc}") from exc


class ArxivClient:
    """Search and fetch papers. Metadata and PDFs are cached under ``cache_dir``."""

    def __init__(self, cache_dir: Path, http_get: HttpGet | None = None, max_retries: int = 3,
                 min_interval: float = 3.0, pdf_extractor: Callable[[Path], str] = extract_pdf_text,
                 sleep: Callable[[float], None] = time.sleep):
        self.cache_dir = Path(cache_dir)
        self._get = http_get or urllib_get
        self.max_retries = max_retries
        self.min_interval = min_interval  # arXiv asks clients to wait ~3 s between API calls
        self._extract = pdf_extractor
        self._sleep = sleep
        self._lock = threading.Lock()
        self._last_call = 0.0

    # -- HTTP ------------------------------------------------------------------------------------
    def _fetch(self, url: str) -> bytes:
        def call() -> bytes:
            with self._lock:
                wait = self.min_interval - (time.monotonic() - self._last_call)
                if wait > 0:
                    self._sleep(wait)
                self._last_call = time.monotonic()
            return self._get(url)

        return with_retries(call, attempts=self.max_retries, sleep=self._sleep, label="arXiv request")

    # -- public API ------------------------------------------------------------------------------
    def search(self, query: str, max_results: int = 5) -> list[Paper]:
        query = (query or "").strip()
        if not query:
            return []
        arxiv_id = find_arxiv_id(query)
        if arxiv_id and _is_mostly_id(query, arxiv_id):
            return [self.resolve(arxiv_id)]
        params = urllib.parse.urlencode({
            "search_query": f"all:{query}", "start": 0, "max_results": max(1, min(max_results, 50)),
            "sortBy": "relevance",
        })
        return parse_atom_feed(self._fetch(f"{API_URL}?{params}"))

    def resolve(self, ref: str) -> Paper:
        arxiv_id = normalize_arxiv_id(ref)
        cached = self._meta_path(arxiv_id)
        if cached.is_file():
            return Paper.from_dict(json.loads(cached.read_text(encoding="utf-8")))
        params = urllib.parse.urlencode({"id_list": arxiv_id, "max_results": 1})
        papers = parse_atom_feed(self._fetch(f"{API_URL}?{params}"))
        if not papers:
            raise PaperNotFound(f"arXiv has no paper with ID {arxiv_id}")
        paper = papers[0]
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(paper.to_dict(), indent=2), encoding="utf-8")
        return paper

    def download_pdf(self, paper: Paper, dest: Path) -> Path:
        cached = self.cache_dir / "pdf" / f"{_safe(paper.arxiv_id)}.pdf"
        if not cached.is_file():
            data = self._fetch(paper.pdf_url or f"https://arxiv.org/pdf/{paper.arxiv_id}")
            if not data.startswith(b"%PDF"):
                raise PaperNotFound(f"download for {paper.arxiv_id} is not a PDF")
            cached.parent.mkdir(parents=True, exist_ok=True)
            tmp = cached.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(cached)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached, dest)
        return dest

    def fetch_fulltext(self, paper: Paper, workdir: Path) -> str:
        pdf = self.download_pdf(paper, Path(workdir) / "paper.pdf")
        return self._extract(pdf)

    def _meta_path(self, arxiv_id: str) -> Path:
        return self.cache_dir / "meta" / f"{_safe(arxiv_id)}.json"


def _safe(arxiv_id: str) -> str:
    return arxiv_id.replace("/", "_")
