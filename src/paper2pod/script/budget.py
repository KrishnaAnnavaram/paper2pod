"""Turn a target duration into per-segment word budgets and token limits.

A long podcast is never generated in one call. Each segment gets its own word budget and a
``max_tokens`` limit sized for that budget, so no single response can be cut off by the limit.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# English prose averages ~1.3 tokens per word; JSON keys, quotes and speaker names add overhead.
TOKENS_PER_WORD = 1.45
TOKEN_HEADROOM = 1.6
JSON_OVERHEAD_TOKENS = 250
MODEL_OUTPUT_LIMIT = 16_000

INTRO_SHARE = 0.08
OUTRO_SHARE = 0.07


@dataclass
class SegmentPlan:
    index: int
    title: str
    kind: str  # "intro" | "body" | "outro"
    target_words: int
    notes: str
    max_tokens: int


def total_word_budget(minutes: float, words_per_minute: int) -> int:
    return int(round(minutes * words_per_minute))


def max_tokens_for_words(words: int) -> int:
    """Generous completion limit for a response of ``words`` words of dialogue."""
    needed = int(math.ceil(words * TOKENS_PER_WORD * TOKEN_HEADROOM)) + JSON_OVERHEAD_TOKENS
    return min(needed, MODEL_OUTPUT_LIMIT)


def _split_evenly(total: int, parts: int) -> list[int]:
    base, extra = divmod(total, parts)
    return [base + (1 if i < extra else 0) for i in range(parts)]


def plan_segments(outline, minutes: float, words_per_minute: int, max_segment_words: int = 650,
                  paper_title: str = "", abstract: str = "") -> list[SegmentPlan]:
    """Allocate the total word budget across intro, outline items and outro.

    Body budgets are proportional to each outline item's weight. Any segment above
    ``max_segment_words`` is split into several parts. The budgets always sum to the total.
    """
    if not outline:
        raise ValueError("cannot plan a script without at least one outline item")
    total = total_word_budget(minutes, words_per_minute)
    intro = max(40, int(total * INTRO_SHARE))
    outro = max(40, int(total * OUTRO_SHARE))
    body_total = total - intro - outro

    # Short podcasts cannot cover every section: keep the heaviest items, in paper order.
    max_items = max(1, body_total // 80)
    if len(outline) > max_items:
        keep = sorted(range(len(outline)), key=lambda i: -outline[i].weight)[:max_items]
        outline = [outline[i] for i in sorted(keep)]

    # Blend with a uniform share so that no section gets a uselessly small budget.
    raw_weights = [max(item.weight, 1e-6) for item in outline]
    n = len(outline)
    shares = [0.7 * w / sum(raw_weights) + 0.3 / n for w in raw_weights]
    exact = [s * body_total for s in shares]
    body = [int(x) for x in exact]
    by_fraction = sorted(range(n), key=lambda i: exact[i] - body[i], reverse=True)
    for i in by_fraction[: body_total - sum(body)]:  # largest-remainder rounding: sums exactly
        body[i] += 1

    overview = "\n".join(f"- {item.title}: {item.summary}" for item in outline)
    raw: list[tuple[str, str, int, str]] = [
        ("Opening", "intro", intro, f"Title: {paper_title}\nAbstract: {abstract}\n\nWhat's ahead:\n{overview}")
    ]
    for item, words in zip(outline, body):
        raw.append((item.title, "body", words, item.notes()))
    raw.append(("Wrap-up", "outro", outro, f"Key takeaways to recap:\n{overview}"))

    plans: list[SegmentPlan] = []
    for title, kind, words, notes in raw:
        parts = max(1, math.ceil(words / max_segment_words))
        for part, part_words in enumerate(_split_evenly(words, parts), start=1):
            label = title if parts == 1 else f"{title} (part {part} of {parts})"
            plans.append(SegmentPlan(index=len(plans), title=label, kind=kind, target_words=part_words,
                                     notes=notes, max_tokens=max_tokens_for_words(part_words)))
    return plans
