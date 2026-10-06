"""Problem 2: one 4,096-token call cannot hold a 30-minute script."""
import pytest

from paper2pod.script.budget import MODEL_OUTPUT_LIMIT, max_tokens_for_words, plan_segments
from paper2pod.script.outline import OutlineItem


def outline(n=6):
    return [OutlineItem(f"Section {i}", f"summary {i}", [f"point {i}"], weight=float(i + 1)) for i in range(n)]


@pytest.mark.parametrize("minutes", [2, 5, 10, 30, 60])
def test_budgets_sum_to_the_requested_length(minutes):
    plans = plan_segments(outline(), minutes, 150, max_segment_words=650)
    assert sum(p.target_words for p in plans) == minutes * 150
    assert plans[0].kind == "intro" and plans[-1].kind == "outro"


def test_long_podcast_is_split_into_segments_that_fit_the_token_limit():
    plans = plan_segments(outline(), 30, 160, max_segment_words=650)
    assert sum(p.target_words for p in plans) == 4800  # the 30-minute case from the analysis
    for p in plans:
        assert p.target_words <= 650
        assert p.max_tokens >= p.target_words * 1.45  # room for every word plus JSON
        assert p.max_tokens <= MODEL_OUTPUT_LIMIT
    assert len(plans) > 8


def test_short_podcast_keeps_only_the_heaviest_sections():
    plans = plan_segments(outline(10), 2, 150)
    body = [p for p in plans if p.kind == "body"]
    assert len(body) <= 2
    assert all(p.target_words > 30 for p in plans)


def test_max_tokens_grows_with_words():
    assert max_tokens_for_words(100) < max_tokens_for_words(600)
    assert max_tokens_for_words(10**6) == MODEL_OUTPUT_LIMIT


def test_empty_outline_is_rejected():
    with pytest.raises(ValueError):
        plan_segments([], 10, 150)
