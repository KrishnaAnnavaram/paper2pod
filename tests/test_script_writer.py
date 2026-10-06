"""Problems 2, 3 and 4: truncated output, unchecked length, and directions mixed into speech."""
import pytest

from conftest import ScriptedLLM, turns_payload, words
from paper2pod.errors import ScriptFormatError
from paper2pod.script.budget import SegmentPlan
from paper2pod.script.generate import ScriptWriter, parse_turns
from paper2pod.script.outline import OutlineItem, build_outline, chunk_text
from paper2pod.models import Section
from paper2pod.services.fakes import FakeLLM
from paper2pod.services.llm import LLMResult


def plan(target=100):
    return SegmentPlan(index=0, title="Method", kind="body", target_words=target, notes="notes", max_tokens=500)


def writer(llm, **kw):
    return ScriptWriter(llm, tolerance=0.1, max_regenerations=kw.pop("max_regenerations", 2), **kw)


def test_parse_turns_validates_speakers_and_keeps_directions_separate(speakers):
    data = {"turns": [
        {"speaker": "alex", "text": "**Alex:** So what is BERT?", "direction": None},
        {"speaker": "Sam", "text": "It is a model (BERT) that reads text both ways [laughs]", "direction": "warm"},
    ]}
    turns = parse_turns(data, speakers)
    assert turns[0].speaker == "Alex" and turns[0].text == "So what is BERT?"
    assert turns[1].text == "It is a model (BERT) that reads text both ways"
    assert turns[1].direction == "warm, laughs"

    with pytest.raises(ScriptFormatError):
        parse_turns({"turns": [{"speaker": "Narrator", "text": "hi", "direction": None}]}, speakers)
    with pytest.raises(ScriptFormatError):
        parse_turns({"script": "free text"}, speakers)


def test_short_draft_is_regenerated_with_feedback(paper, speakers):
    llm = ScriptedLLM([
        LLMResult(turns_payload(("Alex", words(20)), ("Sam", words(20)))),     # 40 words: too short
        LLMResult(turns_payload(("Alex", words(45)), ("Sam", words(52)))),     # 97 words: in range
    ])
    turns, report = writer(llm).write_segment(plan(100), 1, paper, speakers, [])
    assert report.attempts == 2 and report.within_tolerance and report.actual_words == 97
    assert "had 40 words" in llm.calls[1]["user"] and "longer" in llm.calls[1]["user"]


def test_truncated_response_is_retried_with_more_tokens(paper, speakers):
    llm = ScriptedLLM([
        LLMResult({}, finish_reason="length"),
        LLMResult(turns_payload(("Alex", words(50)), ("Sam", words(50)))),
    ])
    _, report = writer(llm).write_segment(plan(100), 1, paper, speakers, [])
    assert report.truncated_responses == 1 and report.within_tolerance
    assert llm.calls[1]["max_tokens"] > llm.calls[0]["max_tokens"]
    assert "cut off" in llm.calls[1]["user"]


def test_overlong_output_is_trimmed_to_budget(paper, speakers):
    long_turn = " ".join(f"Sentence number {i} is here." for i in range(60))  # 300 words
    llm = ScriptedLLM([LLMResult(turns_payload(("Alex", words(30)), ("Sam", long_turn)))] * 3)
    turns, report = writer(llm).write_segment(plan(100), 1, paper, speakers, [])
    assert report.trimmed and report.actual_words <= 110
    assert turns[-1].text.endswith(".")


def test_invalid_speaker_is_retried_then_fails(paper, speakers):
    bad = LLMResult(turns_payload(("Narrator", words(100))))
    llm = ScriptedLLM([bad, bad, bad])
    with pytest.raises(ScriptFormatError):
        writer(llm).write_segment(plan(100), 1, paper, speakers, [])
    assert "Use only these speaker names" in llm.calls[1]["user"]


def test_full_script_with_fake_llm_hits_the_target_length(paper, speakers):
    sections = [Section("Method", "We grow the network one cell at a time. " * 30),
                Section("Results", "Accuracy reaches 91.5% on the toy task. " * 30)]
    llm = FakeLLM()
    outline = build_outline(paper, sections, llm)
    script, reports = ScriptWriter(llm, words_per_minute=150).write(paper, outline, speakers, minutes=12)
    assert abs(script.words - 1800) / 1800 < 0.05
    assert all(r.within_tolerance for r in reports)
    segment_calls = [c for c in llm.calls if c["task"] == "write_segment"]
    assert len(segment_calls) == len(reports) >= 4
    assert script.segment_titles[0] == "Opening" and script.segment_titles[-1] == "Wrap-up"


def test_outline_uses_every_section_not_just_the_first_characters(paper):
    sections = [Section(f"Part {i}", f"Unique fact number {i} is stated here. " * 40) for i in range(4)]
    llm = FakeLLM()
    outline = build_outline(paper, sections, llm, max_items=8)
    assert [o.title for o in outline] == [f"Part {i}" for i in range(4)]
    assert all(f"Unique fact number {i}" in o.summary for i, o in enumerate(outline))


def test_outline_merges_down_to_max_items(paper):
    sections = [Section(f"Part {i}", "Some text that is long enough to stand alone. " * 20) for i in range(12)]
    assert len(build_outline(paper, sections, FakeLLM(), max_items=5)) == 5


def test_chunk_text_respects_limit():
    text = "A sentence that repeats. " * 400
    chunks = chunk_text(text, 1000)
    assert all(len(c) <= 1000 for c in chunks)
    assert sum(c.count("repeats") for c in chunks) == 400


def test_outline_item_notes():
    item = OutlineItem("T", "Summary.", ["one", "two"])
    assert item.notes() == "Summary.\n- one\n- two"
