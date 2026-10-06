"""Problems 3 and 11: length is measured, and scripts are checked against the paper."""
from paper2pod.models import Script, Speaker, Turn
from paper2pod.quality import check_format, check_grounding, check_length, readability, trim_turns

SPEAKERS = [Speaker("Alex", "host"), Speaker("Sam", "expert")]
PAPER = "TRG reaches 91.5% accuracy on 1,000 sequences, using 40% fewer parameters than NAS baselines."


def script(*turns):
    return Script("t", SPEAKERS, [Turn(s, t) for s, t in turns])


def test_length_report_uses_words_and_measured_audio():
    s = script(("Alex", " ".join(["word"] * 140)), ("Sam", " ".join(["word"] * 160)))
    report = check_length(s, minutes=2, words_per_minute=150, tolerance=0.1, audio_seconds=126)
    assert report.target_words == 300 and report.script_words == 300 and report.within_tolerance
    assert report.audio_minutes == 2.1 and report.audio_ratio == 1.05
    assert not check_length(s, minutes=4, words_per_minute=150, tolerance=0.1).within_tolerance


def test_trim_turns_cuts_at_sentence_boundary():
    turns = [Turn("Alex", "One two three four five."), Turn("Sam", "Six seven eight. Nine ten eleven twelve.")]
    trimmed = trim_turns(turns, 8, min_last_turn_words=3)
    assert [t.text for t in trimmed] == ["One two three four five.", "Six seven eight."]


def test_grounding_flags_invented_numbers_and_acronyms():
    s = script(
        ("Sam", "TRG reaches 91.5 percent accuracy on 1000 sequences."),   # supported (format differs)
        ("Sam", "It also beats GPT-4 by 12% on every benchmark."),          # invented
        ("Alex", "So there are two ideas here."),                           # nothing checkable
    )
    report = check_grounding(s, PAPER)
    assert report.checked_sentences == 2 and report.supported_sentences == 1
    assert report.unsupported[0]["tokens"] == ["12%", "GPT-4"]
    assert report.to_dict()["score"] == 0.5


def test_format_checks():
    assert check_format(script(("Alex", "Hi there."), ("Sam", "Hello."))) == []
    issues = check_format(script(("Alex", "**Bold** claim."), ("Alex", "Alex: again"), ("Alex", "and again")))
    text = " ".join(issues)
    assert "Sam never speaks" in text
    assert "markup" in text and "speaker label" in text and "in a row" in text


def test_readability_is_reasonable():
    report = readability(script(("Alex", "The cat sat on the mat. It was happy."), ("Sam", "Yes it was.")))
    assert report.flesch_reading_ease > 80
    assert report.jargon_rate == 0
