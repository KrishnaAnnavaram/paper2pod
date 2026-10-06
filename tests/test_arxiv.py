"""arXiv client: ID handling, feed parsing, search routing, caching and retries (no network)."""
import pytest

from paper2pod.errors import PaperNotFound, TransientError
from paper2pod.sources.arxiv import ArxivClient, find_arxiv_id, normalize_arxiv_id, parse_atom_feed

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2101.00001v2</id>
    <published>2021-01-01T00:00:00Z</published>
    <title>A Synthetic   Paper
      Title</title>
    <summary>An abstract that
      spans lines.</summary>
    <author><name>Ada Example</name></author>
    <author><name>Ben Placeholder</name></author>
    <link href="http://arxiv.org/abs/2101.00001v2" rel="alternate" type="text/html"/>
    <link title="pdf" href="http://arxiv.org/pdf/2101.00001v2" rel="related" type="application/pdf"/>
  </entry>
</feed>"""

ERROR_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry><id>http://arxiv.org/api/errors#incorrect_id_format</id><title>Error</title></entry>
</feed>"""


@pytest.mark.parametrize("text, expected", [
    ("1706.03762", "1706.03762"),
    ("arXiv:1706.03762v7", "1706.03762"),
    ("https://arxiv.org/abs/2401.01234v2", "2401.01234"),
    ("https://arxiv.org/pdf/2401.01234.pdf", "2401.01234"),
    ("please make a podcast of 1706.03762.", "1706.03762"),
    ("https://arxiv.org/abs/hep-th/9901001", "hep-th/9901001"),
    ("math.GT/0309136v1", "math.GT/0309136"),
    ("no identifier here 3.14159", None),
])
def test_find_arxiv_id(text, expected):
    assert find_arxiv_id(text) == expected


def test_normalize_rejects_garbage():
    with pytest.raises(PaperNotFound):
        normalize_arxiv_id("attention is all you need")


def test_parse_atom_feed():
    [paper] = parse_atom_feed(FEED)
    assert paper.arxiv_id == "2101.00001"
    assert paper.title == "A Synthetic Paper Title"
    assert paper.abstract == "An abstract that spans lines."
    assert paper.authors == ["Ada Example", "Ben Placeholder"]
    assert paper.pdf_url.endswith("/pdf/2101.00001v2")
    assert paper.published == "2021-01-01"


def test_error_entries_are_skipped():
    assert parse_atom_feed(ERROR_FEED) == []


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(tmp_path, http):
    return ArxivClient(tmp_path, http_get=http, min_interval=0, sleep=lambda s: None)


def test_query_containing_an_id_resolves_directly(tmp_path):
    """Problem 1: a search whose query holds an arXiv ID used to call another tool and crash."""
    http = FakeHttp([FEED])
    results = client(tmp_path, http).search("can you find arXiv 2101.00001 for me")
    assert [p.arxiv_id for p in results] == ["2101.00001"]
    assert "id_list=2101.00001" in http.urls[0]


def test_free_text_search_uses_search_query(tmp_path):
    http = FakeHttp([FEED])
    client(tmp_path, http).search("growing recurrent networks")
    assert "search_query=all%3Agrowing+recurrent+networks" in http.urls[0]


def test_metadata_is_cached(tmp_path):
    http = FakeHttp([FEED])
    c = client(tmp_path, http)
    first = c.resolve("2101.00001")
    second = c.resolve("https://arxiv.org/abs/2101.00001v2")
    assert first == second and len(http.urls) == 1


def test_unknown_id_raises(tmp_path):
    with pytest.raises(PaperNotFound):
        client(tmp_path, FakeHttp([ERROR_FEED])).resolve("2101.99999")


def test_transient_errors_are_retried(tmp_path):
    http = FakeHttp([TransientError("503"), TransientError("timeout"), FEED])
    assert client(tmp_path, http).resolve("2101.00001").arxiv_id == "2101.00001"
    assert len(http.urls) == 3


def test_pdf_download_is_cached_and_validated(tmp_path):
    [paper] = parse_atom_feed(FEED)
    http = FakeHttp([b"%PDF-1.4 tiny", b"<html>not a pdf</html>"])
    c = client(tmp_path / "cache", http)
    out = c.download_pdf(paper, tmp_path / "job1" / "paper.pdf")
    again = c.download_pdf(paper, tmp_path / "job2" / "paper.pdf")
    assert out.read_bytes() == again.read_bytes() == b"%PDF-1.4 tiny"
    assert len(http.urls) == 1  # second job reused the cache

    other = parse_atom_feed(FEED)[0]
    other.arxiv_id = "2101.00002"
    with pytest.raises(PaperNotFound):
        c.download_pdf(other, tmp_path / "job3" / "paper.pdf")
