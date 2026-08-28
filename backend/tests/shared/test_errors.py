"""Invariant tests for the shared.errors catalog.

These pin the contract every AppError subclass must satisfy — new domain
errors are added all over the codebase, so the guard lives here.
"""

from __future__ import annotations

import re

import pytest

# iter_error_classes() only sees subclasses that have been imported. As
# domains migrate to AppError, import their modules here so this guard covers
# their codes too.
from api.services import tenant_service  # noqa: F401

from shared.errors import (
    ALLOWED_STATUS,
    CODE_RE,
    AppError,
    NotFoundError,
    build_envelope,
    iter_error_classes,
)

_LATIN = re.compile(r"[A-Za-z]")


def _catalog() -> list[type[AppError]]:
    # The backend is importable under two path roots (`services.x` and
    # `api.services.x`), so a migrated module can appear twice as distinct
    # class objects. Dedupe on module basename + qualname.
    by_identity: dict[str, type[AppError]] = {}
    for cls in iter_error_classes():
        key = f"{cls.__module__.rsplit('.', 1)[-1]}.{cls.__qualname__}"
        by_identity.setdefault(key, cls)
    return sorted(by_identity.values(), key=lambda c: c.__name__)


ALL_CLASSES = _catalog()


class TestCatalogInvariants:
    @pytest.mark.parametrize("cls", ALL_CLASSES, ids=lambda c: c.__name__)
    def test_code_shape(self, cls: type[AppError]) -> None:
        assert CODE_RE.match(cls.code), f"{cls.__name__}.code={cls.code!r} is malformed"

    def test_codes_unique(self) -> None:
        seen: dict[str, str] = {}
        for cls in ALL_CLASSES:
            assert cls.code not in seen, (
                f"{cls.__name__} reuses code {cls.code!r} already on {seen[cls.code]}"
            )
            seen[cls.code] = cls.__name__

    @pytest.mark.parametrize("cls", ALL_CLASSES, ids=lambda c: c.__name__)
    def test_status_allowed(self, cls: type[AppError]) -> None:
        assert cls.http_status in ALLOWED_STATUS

    @pytest.mark.parametrize("cls", ALL_CLASSES, ids=lambda c: c.__name__)
    def test_user_message_is_clean_prose(self, cls: type[AppError]) -> None:
        msg = cls.user_message
        assert msg and msg.strip() == msg
        assert len(msg) <= 30, f"{cls.__name__}: message too long ({len(msg)} chars)"
        assert not msg.endswith(("。", ".")), f"{cls.__name__}: trailing period"
        assert "\n" not in msg
        assert not _LATIN.search(msg), (
            f"{cls.__name__}: user_message contains Latin letters — no technical terms"
        )
        assert cls.code not in msg


class TestAppErrorBehaviour:
    def test_init_is_keyword_only(self) -> None:
        # A positional arg would let an internal value leak into user_message.
        with pytest.raises(TypeError):
            NotFoundError("some-internal-id")  # type: ignore[misc]

    def test_instance_user_message_override(self) -> None:
        err = NotFoundError(user_message="找不到這個計時器")
        assert err.user_message == "找不到這個計時器"

    def test_context_never_reaches_envelope(self) -> None:
        err = NotFoundError(context={"channel_id": "12345", "raw": "KeyError: x"})
        env = err.to_envelope(request_id="req-1")
        flat = repr(env)
        assert "12345" not in flat
        assert "KeyError" not in flat
        assert env["error"]["request_id"] == "req-1"
        assert env["detail"] == env["error"]["message"]

    def test_fields_surface_in_envelope(self) -> None:
        err = NotFoundError(fields={"name": "這個欄位是必填的"})
        env = err.to_envelope(request_id=None)
        assert env["error"]["fields"] == {"name": "這個欄位是必填的"}

    def test_build_envelope_shape(self) -> None:
        env = build_envelope(code="TIMER.NOT_FOUND", message="找不到", request_id="r")
        assert env == {
            "detail": "找不到",
            "error": {
                "code": "TIMER.NOT_FOUND",
                "message": "找不到",
                "request_id": "r",
                "fields": None,
            },
        }
