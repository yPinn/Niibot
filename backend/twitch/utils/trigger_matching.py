"""Pattern matching logic for message triggers.

Supported match types:
    contains    — trigger.pattern appears anywhere in text
    startswith  — text begins with trigger.pattern
    exact       — text equals trigger.pattern exactly
    regex       — re.search(trigger.pattern, text) matches

A trigger may also carry an ``aliases`` field (comma-separated strings).
``match_trigger`` checks the primary pattern first, then each alias.
Any match returns True.

ReDoS protection
----------------
Call ``validate_regex_pattern(pattern)`` before persisting any user-supplied
regex trigger.  It runs ``re.search`` against a catastrophic-backtracking
canary inside a subprocess (separate GIL), killing the process if it exceeds
``_VALIDATE_TIMEOUT`` seconds.  Patterns that survive are safe to use at
match time without any additional overhead.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Protocol

# ---------------------------------------------------------------------------
# ReDoS validation (called once at trigger creation, not at match time)
# ---------------------------------------------------------------------------

_REDOS_CANARY = "a" * 30 + "b"  # classic catastrophic-backtracking canary
_VALIDATE_TIMEOUT = 1.5  # seconds — subprocess is killed if it runs longer


def validate_regex_pattern(pattern: str) -> bool:
    """Return True if *pattern* is a valid, ReDoS-safe regex.

    Runs ``re.search(pattern, canary)`` inside a fresh subprocess so that a
    catastrophically backtracking pattern cannot block (or hold the GIL of)
    the calling process.  Returns False if:

    * the pattern is syntactically invalid, or
    * the subprocess exceeds ``_VALIDATE_TIMEOUT`` seconds.
    """
    try:
        re.compile(pattern)
    except re.error:
        return False

    env = {**os.environ, "_NII_PATTERN": pattern, "_NII_CANARY": _REDOS_CANARY}
    code = "import re, os; re.search(os.environ['_NII_PATTERN'], os.environ['_NII_CANARY'])"
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            timeout=_VALIDATE_TIMEOUT,
            capture_output=True,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False


# ---------------------------------------------------------------------------
# Match-time logic (patterns are pre-validated — no extra protection needed)
# ---------------------------------------------------------------------------


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
            return bool(re.search(pat, cmp))
        except re.error:
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
