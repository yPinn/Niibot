"""Application error catalog.

The single place that ties three things together for one failure mode:

* ``code``          — a stable machine identifier (``TIMER.NOT_FOUND``). Never
                      changes once shipped; safe to branch on in the frontend
                      and to grep for in logs. **Never shown to a user.**
* ``http_status``   — the response status.
* ``user_message``  — the polished, human sentence the end user sees.

Because ``code`` and ``user_message`` live on the same class there is no
separate message table to drift out of sync. ``tests/shared/test_errors.py``
pins the invariants below.

user_message writing rules (enforced by the test):

* One sentence, up to ~40 characters. No line breaks, no trailing period.
* Say *what happened + what to do next*, never the mechanism.
    OK   「儲存失敗，請稍後再試」  「這個名稱已經有人用了，換一個吧」
    NOT  「資料庫連線逾時」        「Upstream API 回傳 502」
* Must not contain: HTTP status codes, exception class names, technical
  jargon, internal field/program names, stack traces, internal IDs, or the
  error code itself. Recognisable brand names (YouTube, Twitch, ...) are ok —
  see _ALLOWED_WORDS.
* Address the user as 「你」. For server-side faults, take responsibility
  (「系統暫時出了點狀況」, not 「發生未知錯誤」). For 4xx, state it neutrally —
  do not blame the user.
* The same logical error uses the same sentence everywhere.

Anything sensitive or diagnostic (the original exception text, a channel_id,
etc.) goes in ``context`` — it is logged, never returned to the client.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Mapping
from typing import Any, ClassVar

#: Valid ``code`` shape: ``<DOMAIN>.<REASON>``, both SCREAMING_SNAKE.
CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*$")

#: Status codes an ``AppError`` subclass is allowed to declare.
ALLOWED_STATUS = frozenset({400, 401, 403, 404, 409, 422, 429, 500, 502, 503, 504})


def build_envelope(
    *,
    code: str,
    message: str,
    request_id: str | None,
    fields: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """The canonical error response body.

    ``detail`` is kept (and equal to ``message``) for backward compatibility
    with clients that read the old FastAPI ``{"detail": ...}`` shape.
    """
    return {
        "detail": message,
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "fields": dict(fields) if fields else None,
        },
    }


class AppError(Exception):
    """Base class for every deliberately-raised application error."""

    code: ClassVar[str] = "INTERNAL.UNEXPECTED"
    http_status: ClassVar[int] = 500
    #: Log level the API exception handler uses for this error.
    log_level: ClassVar[int] = logging.ERROR
    #: Class default; may be overridden per-instance via the constructor.
    user_message: str = "系統暫時出了點狀況，請稍後再試"

    def __init__(
        self,
        *,
        user_message: str | None = None,
        context: Mapping[str, Any] | None = None,
        fields: Mapping[str, str] | None = None,
    ) -> None:
        # keyword-only on purpose: a positional first arg would let callers
        # accidentally pipe an internal value (channel_id, str(exc)) straight
        # into the user-visible message.
        self.user_message = user_message or type(self).user_message
        self.context: dict[str, Any] = dict(context or {})
        self.fields: dict[str, str] | None = dict(fields) if fields else None
        super().__init__(f"{self.code}: {self.user_message}")

    def to_envelope(self, request_id: str | None) -> dict[str, Any]:
        return build_envelope(
            code=self.code,
            message=self.user_message,
            request_id=request_id,
            fields=self.fields,
        )


# ── Generic subclasses ──────────────────────────────────────────────────────
# Domain-specific errors live next to their raiser and subclass one of these,
# overriding ``code`` (and usually ``user_message``).


class NotFoundError(AppError):
    code = "INTERNAL.NOT_FOUND"
    http_status = 404
    user_message = "找不到你要的資料"
    log_level = logging.INFO


class ConflictError(AppError):
    code = "INTERNAL.ALREADY_EXISTS"
    http_status = 409
    user_message = "這筆資料已經存在了"
    log_level = logging.INFO


class InvalidInputError(AppError):
    # Domain-level rejection of a semantically bad value. FastAPI's own
    # request-shape failures use VALIDATION.INVALID_INPUT (422); this is 400.
    code = "INPUT.INVALID"
    http_status = 400
    user_message = "輸入的內容有誤，請檢查後再試"
    log_level = logging.INFO


class AccessDeniedError(AppError):
    code = "AUTH.ACCESS_DENIED"
    http_status = 403
    user_message = "你沒有權限執行這個操作"
    log_level = logging.WARNING


class RateLimitedError(AppError):
    code = "INTERNAL.LIMIT_EXCEEDED"
    http_status = 429
    user_message = "操作太頻繁了，請稍等一下再試"
    log_level = logging.WARNING


class UpstreamError(AppError):
    code = "INTERNAL.UPSTREAM_FAILED"
    http_status = 502
    user_message = "外部服務暫時沒有回應，請稍後再試"
    log_level = logging.ERROR


def iter_error_classes(root: type[AppError] = AppError) -> Iterator[type[AppError]]:
    """Depth-first walk of every ``AppError`` subclass currently imported."""
    yield root
    for sub in root.__subclasses__():
        yield from iter_error_classes(sub)


# Brand / product names that are fine to show a non-technical user.
_ALLOWED_WORDS = {
    "youtube",
    "twitch",
    "bilibili",
    "discord",
    "obs",
    "ai",
    "paypal",
    "ecpay",
    "opay",
    "newebpay",
    "bot",
    "valorant",
    "tft",
}
_WORD_RE = re.compile(r"[A-Za-z]+")


def validate_catalog() -> list[str]:
    """Return a list of contract violations across all imported AppError
    subclasses (empty = healthy). Used by tests and startup checks.

    The backend is importable under two path roots (``services.x`` and
    ``api.services.x``); dedupe on module basename + qualname so a migrated
    module isn't double-counted.
    """
    seen: dict[str, str] = {}
    problems: list[str] = []
    codes: dict[str, str] = {}
    for cls in iter_error_classes():
        key = f"{cls.__module__.rsplit('.', 1)[-1]}.{cls.__qualname__}"
        if key in seen:
            continue
        seen[key] = cls.__name__

        if not CODE_RE.match(cls.code):
            problems.append(f"{cls.__name__}: malformed code {cls.code!r}")
        if cls.code in codes and codes[cls.code] != key:
            problems.append(f"{cls.__name__}: code {cls.code!r} already on {codes[cls.code]}")
        codes[cls.code] = key

        if cls.http_status not in ALLOWED_STATUS:
            problems.append(f"{cls.__name__}: status {cls.http_status} not allowed")

        msg = cls.user_message
        bad_words = [w for w in _WORD_RE.findall(msg) if w.lower() not in _ALLOWED_WORDS]
        if not msg or msg.strip() != msg or len(msg) > 40 or "\n" in msg:
            problems.append(f"{cls.__name__}: user_message not clean prose ({msg!r})")
        elif bad_words or cls.code in msg:
            problems.append(
                f"{cls.__name__}: user_message leaks tech text {bad_words or cls.code!r} ({msg!r})"
            )
    return problems
