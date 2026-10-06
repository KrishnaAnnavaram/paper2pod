"""Problem 10: weak PDF parsing (numbered headings missed, back matter kept, sections unused)."""
from paper2pod.parsing.cleaning import clean_text, unwrap_lines
from paper2pod.parsing.pdf import order_blocks
from paper2pod.parsing.sections import detect_heading, paper_sections
from paper2pod.sources.local import sample_paper_text


def test_numbered_and_plain_headings_are_detected():
    assert detect_heading("1 Introduction") == "Introduction"
    assert detect_heading("3.2 Scaled Dot-Product Attention") == "Scaled Dot-Product Attention"
    assert detect_heading("IV. EXPERIMENTAL RESULTS") == "Experimental Results"
    assert detect_heading("Related Work") == "Related Work"
    assert detect_heading("ABSTRACT") == "Abstract"
    assert detect_heading("Appendix B Proofs") == "Appendix B Proofs"


def test_prose_and_table_rows_are_not_headings():
    assert detect_heading("We evaluate on a toy benchmark of 1,000 synthetic sequences of length 50, split") is None
    assert detect_heading("2 Transformer 28.4 41.8") is None
    assert detect_heading("200 for testing. The fixed-size baseline uses 64 hidden cells.") is None
    assert detect_heading("A. Example and B. Placeholder") is None
    assert detect_heading("") is None


def test_clean_text_fixes_ligatures_hyphens_and_page_furniture():
    raw = "The eﬃcient repre-\nsentation\n12\narXiv:1706.03762v7 [cs.CL] 2 Aug 2023\nworks   well"
    cleaned = clean_text(raw)
    assert "efficient" in cleaned and "representation" in cleaned
    assert "arXiv:" not in cleaned and "\n12\n" not in cleaned
    assert "works well" in cleaned


def test_unwrap_lines_keeps_paragraphs():
    assert unwrap_lines("one\ntwo\n\nthree\nfour") == "one two\n\nthree four"


def test_sample_paper_sections_drop_references_and_appendix():
    sections = paper_sections(sample_paper_text())
    titles = [s.title for s in sections]
    assert titles[:3] == ["Abstract", "Introduction", "Related Work"]
    assert "Growth Rule" in titles and "Conclusion" in titles
    assert not any("Reference" in t or "Appendix" in t for t in titles)
    body = " ".join(s.text for s in sections)
    assert "made-up reference" not in body and "should also be dropped" not in body
    assert "\n" not in sections[1].text  # hard wraps were joined


def test_two_column_blocks_are_read_column_by_column():
    width = 600
    title = (50, 10, 550, 40, "Title")
    left_top, left_bottom = (50, 60, 290, 200, "L1"), (50, 210, 290, 400, "L2")
    right_top, right_bottom = (310, 60, 550, 200, "R1"), (310, 210, 550, 400, "R2")
    figure = (50, 420, 550, 500, "Wide figure")
    after_left, after_right = (50, 510, 290, 600, "L3"), (310, 510, 550, 600, "R3")
    blocks = [right_bottom, left_top, title, right_top, left_bottom, after_right, figure, after_left]
    order = [b[4] for b in order_blocks(blocks, width)]
    assert order == ["Title", "L1", "L2", "R1", "R2", "Wide figure", "L3", "R3"]
