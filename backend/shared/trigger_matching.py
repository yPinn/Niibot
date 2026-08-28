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
Two layers, because ``re`` holds the GIL and cannot be interrupted mid-match:

1. Creation time — call ``validate_regex_pattern(pattern)`` before persisting
   any user-supplied regex trigger.  It runs the pattern against a family of
   catastrophic-backtracking canaries (varied character classes) inside a
   subprocess, killing the process if it exceeds ``_VALIDATE_TIMEOUT`` seconds.
2. Match time — ``_match_single`` truncates the input to ``_MATCH_INPUT_CAP``
   characters before ``re.search``.  Bounding the input length caps the
   backtracking blow-up for any pattern that slipped past layer 1.
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

# A single "a"*n + "b" canary only exercises patterns that backtrack on word
# characters.  Cover the common classes an attacker would target: digits,
# whitespace, punctuation, mixed alphanumeric and mixed case.  Each ends in a
# character that forces the final sub-expression to fail, provoking the blow-up.
_REDOS_CANARIES: tuple[str, ...] = (
    "a" * 40 + "!",
    "1" * 40 + "!",
    " " * 40 + "!",
    "/" * 40 + "!",
    "a1" * 20 + "!",
    "aA" * 20 + "!",
)
_VALIDATE_TIMEOUT = 2.0  # seconds — subprocess is killed if it runs longer

# Upper bound on the text handed to re.search at match time.  Twitch chat
# messages are capped at 500 chars; anything longer is not a legitimate match
# target and only serves to widen a ReDoS window.
_MATCH_INPUT_CAP = 512


def validate_regex_pattern(pattern: str) -> bool:
    """Return True if *pattern* is a valid, ReDoS-safe regex.

    Runs ``re.search(pattern, canary)`` for every canary inside a single fresh
    subprocess so that a catastrophically backtracking pattern cannot block (or
    hold the GIL of) the calling process.  Returns False if:

    * the pattern is syntactically invalid, or
    * the subprocess exceeds ``_VALIDATE_TIMEOUT`` seconds on any canary.
    """
    try:
        re.compile(pattern)
    except re.error:
        return False

    # Newline-separate the canaries: env vars cannot hold NUL bytes, and none of
    # the canaries contain a newline.
    env = {
        **os.environ,
        "_NII_PATTERN": pattern,
        "_NII_CANARIES": "\n".join(_REDOS_CANARIES),
    }
    code = (
        "import re, os; p = os.environ['_NII_PATTERN']; "
        "[re.search(p, c) for c in os.environ['_NII_CANARIES'].split(chr(10))]"
    )
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
# Match-time logic (patterns are pre-validated; input length is still capped)
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
            return bool(re.search(pat, cmp[:_MATCH_INPUT_CAP]))
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
