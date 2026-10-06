"""paper2pod: turn arXiv papers into multi-voice podcasts.

The package is a pipeline of plain, testable functions (fetch -> parse -> outline -> script ->
validate -> tts -> mix). External services sit behind small adapters in ``paper2pod.services``.
"""

__version__ = "0.1.0"
