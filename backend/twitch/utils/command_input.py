"""Normalisation for chat command arguments.

Viewers type on phones mid-stream, so arguments arrive with stray symbols
(`!game ;lol'`), full-width punctuation from a CJK IME (`＃`, `，`, `；`),
pasted URLs, and extra whitespace. These helpers turn that into the clean value
a command needs, or None when nothing usable is left, so each command can reply
with a usage hint instead of a misleading "not found".

Only apply them to identifier-like arguments (names, logins, numbers). Free
text (titles, quotes, AI prompts) must reach the handler untouched.
"""

from __future__ import annotations

import re
import string
import unicodedata

# Symbols that land next to a word by accident: home-row `;` `'`, quote pairs,
# separators, and their full-width / CJK counterparts. Deliberately excludes
# `!` `?` `&` `-` and brackets, which can end a real name ("Jeopardy!"). Only
# the ends are ever trimmed, so inner symbols survive ("Fall Guys: Ultimate").
_STRAY = ";:'\"`~,.|\\/" + "；：‘’“”，。、｜＼／「」『』"
_EDGE = _STRAY + " \t　"

_LOGIN_PUNCT = string.punctuation.replace("_", "")
_LOGIN = re.compile(r"[a-z0-9_]{1,25}")
_TWITCH_URL = re.compile(r"twitch\.tv/([A-Za-z0-9_]+)", re.IGNORECASE)
_TAG_SEPARATORS = re.compile(r"[,，、;；\s]+")
_NUMBER = re.compile(r"[0-9]+", re.ASCII)


def clean_text(raw: str | None) -> str:
    """Trim stray symbols from both ends and collapse inner whitespace."""
    return " ".join((raw or "").strip(_EDGE).split()).strip(_EDGE)


def parse_login(raw: str | None) -> str | None:
    """Extract a Twitch login from `name`, `@name` or a twitch.tv URL.

    Returns the first token that is a complete valid login. A token with any
    non-login character inside (a CJK display name, `小明_abc`) is rejected
    rather than trimmed, so we never resolve to a different channel than the
    one the viewer meant.
    """
    text = unicodedata.normalize("NFKC", raw or "")
    if match := _TWITCH_URL.search(text):
        return match.group(1).lower()
    for token in text.split():
        candidate = token.lstrip("@＠").strip(_LOGIN_PUNCT).lower()
        if _LOGIN.fullmatch(candidate):
            return candidate
    return None


def parse_riot_id(raw: str | None) -> tuple[str, str] | None:
    """Split `Name#TAG` into (name, tag). Names may contain spaces."""
    text = clean_text((raw or "").replace("＃", "#"))
    name, sep, tag = text.partition("#")
    name = clean_text(name)
    tag = "".join(clean_text(tag).lstrip("#").split())
    if not sep or not name or not tag:
        return None
    return name, tag


def split_tags(raw: str | None) -> list[str]:
    """Split a tag list on spaces / commas / `、` / `;`, dropping `#` prefixes
    and duplicates (Twitch tags are case-insensitive)."""
    seen: set[str] = set()
    tags: list[str] = []
    for part in _TAG_SEPARATORS.split(raw or ""):
        tag = part.lstrip("#＃").strip(_EDGE)
        if tag and tag.casefold() not in seen:
            seen.add(tag.casefold())
            tags.append(tag)
    return tags


def parse_number(raw: str | None) -> int | None:
    """Parse `3`, `#3`, `３` or `3;` into an int; None for anything else."""
    text = unicodedata.normalize("NFKC", clean_text(raw)).lstrip("#")
    return int(text) if _NUMBER.fullmatch(text) else None
