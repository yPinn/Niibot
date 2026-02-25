"""Pattern matching logic for message triggers.

Supported match types:
    contains    — trigger.pattern appears anywhere in text
    startswith  — text begins with trigger.pattern
    exact       — text equals trigger.pattern exactly
    regex       — re.search(trigger.pattern, text) matches
"""

from __future__ import annotations

import re
from typing import Protocol


class TriggerLike(Protocol):
    """Minimal trigger interface required by match_trigger."""

    pattern: str
    match_type: str
    case_sensitive: bool


def match_trigger(trigger: TriggerLike, text: str) -> bool:
    """Return True if *text* matches the trigger's pattern/type.

    When case_sensitive is False both the pattern and the incoming text are
    lowercased before comparison so the match is case-insensitive.
    Unknown match_type values are treated as no-match (returns False).
    Invalid regex patterns do not raise; they return False.
    """
    pat = trigger.pattern if trigger.case_sensitive else trigger.pattern.lower()
    cmp = text if trigger.case_sensitive else text.lower()

    if trigger.match_type == "contains":
        return pat in cmp
    if trigger.match_type == "startswith":
        return cmp.startswith(pat)
    if trigger.match_type == "exact":
        return cmp == pat
    if trigger.match_type == "regex":
        try:
            return bool(re.search(pat, cmp))
        except re.error:
            return False
    return False
