"""Retry with exponential backoff for calls to external services."""
from __future__ import annotations

import logging
import random
import time
from typing import Callable, TypeVar

from .errors import TransientError

T = TypeVar("T")
log = logging.getLogger(__name__)


def with_retries(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retry_on: tuple[type[BaseException], ...] = (TransientError,),
    sleep: Callable[[float], None] = time.sleep,
    label: str = "call",
) -> T:
    """Call ``fn`` until it succeeds, retrying only on ``retry_on`` errors.

    Delays grow as ``base_delay * 2**n`` (capped at ``max_delay``) with a little jitter.
    Errors that are not retryable propagate immediately.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except retry_on as exc:
            if attempt == attempts:
                raise
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay *= 1 + random.uniform(0, 0.1)
            log.warning("%s failed (%s); retry %d/%d in %.1fs", label, type(exc).__name__,
                        attempt, attempts - 1, delay)
            sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
