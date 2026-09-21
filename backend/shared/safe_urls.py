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
_TRIM_CHARS = "\"'<>[](){}，。！？、,;"


def _parse_http_token(token: str) -> SplitResult | None:
    candidate = token.strip(_TRIM_CHARS)
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
