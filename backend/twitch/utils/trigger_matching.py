"""Pattern matching logic for message triggers.

Supported match types:
    contains    — trigger.pattern appears anywhere in text
    startswith  — text begins with trigger.pattern
    exact       — text equals trigger.pattern exactly
    regex       — re.search(trigger.pattern, text) matches

A trigger may also carry an ``aliases`` field (comma-separated strings).
``match_trigger`` checks the primary pattern first, then each alias.
Any match returns True.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Protocol

_regex_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="regex")
_REGEX_TIMEOUT = 0.5  # seconds — rejects catastrophic backtracking before it stalls the event loop


class TriggerLike(Protocol):
    """Minimal trigger interface required by match_trigger."""

    pattern: str
    match_type: str
    case_sensitive: bool
    aliases: str | None


def _match_single(pattern: str, match_type: str, case_sensitive: bool, text: str) -> bool:
    """Return True if *text* matches *pattern* using *match_type*."""
    pat = pattern if case_sensitive else pattern.lower()
    cmp = text if case_sensitive else text.lower()

    if match_type == "contains":
        return pat in cmp
    if match_type == "startswith":
        return cmp.startswith(pat)
    if match_type == "exact":
        return cmp == pat
    if match_type == "regex":
        try:
            future = _regex_pool.submit(re.search, pat, cmp)
            return bool(future.result(timeout=_REGEX_TIMEOUT))
        except (re.error, FuturesTimeoutError):
            return False
    return False


def match_trigger(trigger: TriggerLike, text: str) -> bool:
    """Return True if *text* matches the trigger's pattern OR any of its aliases.

    When case_sensitive is False both the pattern and the incoming text are
    lowercased before comparison so the match is case-insensitive.
    Unknown match_type values are treated as no-match (returns False).
    Invalid regex patterns do not raise; they return False.
    """
    if _match_single(trigger.pattern, trigger.match_type, trigger.case_sensitive, text):
        return True

    if trigger.aliases:
        for alias in trigger.aliases.split(","):
            alias = alias.strip()
            if alias and _match_single(alias, trigger.match_type, trigger.case_sensitive, text):
                return True

    return False
