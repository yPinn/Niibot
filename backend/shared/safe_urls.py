"""Small URL-validation primitives for user-supplied public links.

The helpers deliberately compare parsed hostnames instead of searching raw text.
Callers may still accept a URL embedded in chat text, but a provider-looking
substring in an attacker-controlled host or path is never treated as trusted.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from urllib.parse import SplitResult, urljoin, urlsplit

_HTTP_SCHEMES = frozenset({"http", "https"})
# Punctuation a pasted URL commonly ends up wrapped in: straight quotes/brackets,
# smart/curly quotes (iOS/autocorrect turns ' into '), and the CJK quotation
# and title-mark brackets Traditional Chinese users reach for when quoting a
# link in chat (「連結」, 《標題》, （備註） etc).
_TRIM_CHARS = (
    "\"'<>[](){}，。！？、,;"
    "‘’“”"  # ' ' " "
    "「」『』《》〈〉【】（）"
)
# Zero-width/format characters a mobile keyboard or paste-from-app can leave
# inside otherwise-correct text (invisible, so a user has no way to notice or
# manually remove one) — stripped from anywhere in the token, not just the
# edges, since one can land in the middle of a copy-pasted URL.
#
# Built from codepoints rather than embedding the (invisible, by definition)
# characters directly in this source file — a formatter would otherwise
# happily collapse a unicode-escape string literal back into the literal
# character, leaving something unreviewable sitting in a diff. See
# test_safe_urls.py for the same convention.
_INVISIBLE_CODEPOINTS = (
    0x200B,  # ZERO WIDTH SPACE
    0x200C,  # ZERO WIDTH NON-JOINER
    0x200D,  # ZERO WIDTH JOINER
    0x2060,  # WORD JOINER
    0xFEFF,  # ZERO WIDTH NO-BREAK SPACE / BOM
)
_INVISIBLE_RE = re.compile("[" + "".join(chr(cp) for cp in _INVISIBLE_CODEPOINTS) + "]")


def _parse_http_token(token: str) -> SplitResult | None:
    candidate = _INVISIBLE_RE.sub("", token).strip(_TRIM_CHARS)
    if not candidate:
        return None
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() not in _HTTP_SCHEMES
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
    ):
        return None
    return parsed


def iter_http_urls(text: str) -> Iterator[SplitResult]:
    """Yield syntactically safe HTTP(S) URLs found in whitespace-delimited text."""
    for token in re.split(r"\s+", text.strip()):
        parsed = _parse_http_token(token)
        if parsed is not None:
            yield parsed


def find_allowed_http_url(text: str, allowed_hosts: frozenset[str]) -> SplitResult | None:
    """Return the first URL whose parsed hostname exactly matches ``allowed_hosts``."""
    for parsed in iter_http_urls(text):
        if parsed.hostname and parsed.hostname.lower() in allowed_hosts:
            return parsed
    return None


def parse_allowed_absolute_url(url: str, allowed_hosts: frozenset[str]) -> SplitResult | None:
    """Validate one absolute redirect target against an exact hostname allowlist."""
    if re.search(r"\s", url):
        return None
    parsed = _parse_http_token(url)
    if parsed is None or parsed.hostname is None:
        return None
    return parsed if parsed.hostname.lower() in allowed_hosts else None


def allowed_redirect_target(
    current_url: str,
    location: str,
    allowed_hosts: frozenset[str],
) -> str | None:
    """Resolve and validate a redirect location before any request is sent to it."""
    target = urljoin(current_url, location)
    return target if parse_allowed_absolute_url(target, allowed_hosts) is not None else None
