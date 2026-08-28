"""Contract tests for the shared.errors catalog."""

from __future__ import annotations

import pytest

# Importing tenant_service registers its AppError subclasses so
# validate_catalog() covers them. Router-defined codes are swept in
# tests/api/test_error_catalog.py (that path can import routers).
from api.services import tenant_service  # noqa: F401

from shared.errors import (
    NotFoundError,
    build_envelope,
    validate_catalog,
)


def test_catalog_is_clean() -> None:
    problems = validate_catalog()
    assert not problems, "\n".join(problems)


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
