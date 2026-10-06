"""Exception types shared across the package."""
from __future__ import annotations


class Paper2PodError(Exception):
    """Base class for all errors raised on purpose by this package."""


class ConfigError(Paper2PodError):
    """The configuration is missing a value or holds an invalid one."""


class MissingDependency(Paper2PodError):
    """An optional extra is needed for this feature."""

    def __init__(self, package: str, extra: str):
        super().__init__(f"'{package}' is not installed. Install it with: pip install \"paper2pod[{extra}]\"")
        self.package, self.extra = package, extra


class TransientError(Paper2PodError):
    """A failure worth retrying (rate limit, timeout, 5xx, dropped connection)."""


class PaperNotFound(Paper2PodError):
    """The requested paper does not exist or could not be resolved."""


class ScriptFormatError(Paper2PodError):
    """The model returned a script that does not match the expected structure."""


class JobCancelled(Paper2PodError):
    """Raised inside the pipeline when the user cancels a running job."""
