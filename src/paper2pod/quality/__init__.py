"""Checks run on every script: length, format, grounding in the paper and readability."""
from .factuality import GroundingReport, check_grounding
from .format import check_format
from .length import LengthReport, check_length, trim_turns
from .readability import ReadabilityReport, readability

__all__ = ["GroundingReport", "LengthReport", "ReadabilityReport", "check_format", "check_grounding",
           "check_length", "readability", "trim_turns"]
