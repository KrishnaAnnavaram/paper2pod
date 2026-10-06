"""Problems 4 and 5: content lost to direction-stripping regexes, and a wrong voice map."""
import math
import struct

import pytest

from paper2pod.audio.mix import mix_clips, normalize_loudness, rms_and_peak, wav_duration, write_wav
from paper2pod.audio.text import chunk_for_tts
from paper2pod.audio.voices import OPENAI_VOICES, assign_voices
from paper2pod.models import Speaker
from paper2pod.services.fakes import FakeTTS
from paper2pod.text_utils import strip_markup


def test_parentheses_and_math_survive_cleaning():
    text, cue = strip_markup("We use (BERT) and f(x) = (a + b) * c, a *really* important idea.")
    assert "(BERT)" in text and "f(x) = (a + b)" in text
    assert "really important idea" in text and "*" not in text.replace("(a + b) * c", "")
    assert cue is None


def test_bracketed_cues_move_out_of_the_text_but_brackets_with_content_stay():
    text, cue = strip_markup("[laughs] Exactly, the interval [0, 1] matters. [pause]")
    assert text == "Exactly, the interval [0, 1] matters."
    assert cue == "laughs, pause"


def test_speaker_label_is_removed():
    assert strip_markup("**Sam:** Hello there", ["Sam"])[0] == "Hello there"


def test_chunking_respects_limit_and_keeps_every_word():
    text = " ".join(f"Sentence {i} has a handful of words in it." for i in range(400))
    chunks = chunk_for_tts(text, 4000)
    assert len(chunks) > 1 and all(len(c) <= 4000 for c in chunks)
    assert " ".join(chunks).split() == text.split()


def test_chunking_splits_a_single_huge_sentence():
    text = "word " * 2000
    chunks = chunk_for_tts(text.strip(), 500)
    assert all(len(c) <= 500 for c in chunks)
    assert sum(len(c.split()) for c in chunks) == 2000


def test_voice_catalog_styles_are_correct():
    styles = {v.name: v.style for v in OPENAI_VOICES}
    assert styles["nova"] == styles["shimmer"] == "female"
    assert styles["onyx"] == styles["echo"] == "male"


def test_voices_match_style_and_are_distinct():
    speakers = [Speaker("A", "host", "female"), Speaker("B", "expert", "female"),
                Speaker("C", "guest", "male"), Speaker("D", "guest", "male")]
    voices = assign_voices(speakers)
    assert {voices["A"], voices["B"]} == {"nova", "shimmer"}
    assert {voices["C"], voices["D"]} == {"onyx", "echo"}
    assert len(set(voices.values())) == 4


def test_third_female_speaker_falls_back_to_a_neutral_voice():
    speakers = [Speaker(n, "guest", "female") for n in "ABC"]
    assert assign_voices(speakers)["C"] in {"alloy", "fable"}


def test_overrides_and_pinned_voices_win_and_duplicates_fail():
    speakers = [Speaker("Alex", "host", "female"), Speaker("Sam", "expert", "male", voice="nova")]
    voices = assign_voices(speakers, overrides={"alex": "fable"})
    assert voices == {"Alex": "fable", "Sam": "nova"}
    with pytest.raises(ValueError):
        assign_voices(speakers, overrides={"Alex": "nova"})
    with pytest.raises(ValueError):
        assign_voices([Speaker("X", voice="robot")])
    with pytest.raises(ValueError):
        assign_voices([Speaker(str(i)) for i in range(7)])


def tone(seconds, rate=8000, amp=0.5):
    n = int(seconds * rate)
    return struct.pack(f"<{n}h", *(int(amp * 32767 * math.sin(2 * math.pi * 200 * i / rate)) for i in range(n)))


def test_loudness_normalisation_evens_out_clips():
    quiet, loud = normalize_loudness(tone(0.5, amp=0.05)), normalize_loudness(tone(0.5, amp=0.9))
    assert abs(rms_and_peak(quiet)[0] - rms_and_peak(loud)[0]) < 0.01
    assert rms_and_peak(loud)[1] <= 0.96


def test_mix_writes_wav_with_chapters_and_measured_duration(tmp_path):
    clips = [(0, tone(1.0)), (0, tone(1.0)), (1, tone(2.0))]
    pcm, chapters = mix_clips(clips, ["Opening", "Method"], 8000, pause_ms=500)
    path = write_wav(tmp_path / "out.wav", pcm, 8000)
    assert wav_duration(path) == pytest.approx(1 + 0.5 + 1 + 1.0 + 2, abs=0.01)
    assert [c.title for c in chapters] == ["Opening", "Method"]
    assert chapters[1].start_seconds == pytest.approx(3.5, abs=0.01)


def test_fake_tts_duration_follows_word_count():
    tts = FakeTTS(sample_rate=8000, words_per_minute=150)
    pcm = tts.synthesize(" ".join(["word"] * 150), "nova")
    assert len(pcm) == 60 * 8000 * 2
    with pytest.raises(ValueError):
        tts.synthesize("x" * 5000, "nova")
