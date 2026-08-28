"""Tests for shared.logging_setup — the structlog-backed logging pipeline."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest
import structlog

from shared.logging_setup import setup_logging

_REQUIRED_KEYS = {"timestamp", "level", "logger", "mod", "own", "service", "event"}


@pytest.fixture
def json_logs(monkeypatch: pytest.MonkeyPatch) -> Iterator[io.StringIO]:
    """setup_logging() in JSON mode with stdout captured to a buffer."""
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    setup_logging(
        log_level="DEBUG",
        service_name="api",
        own_prefixes=("routers.", "shared."),
        console=False,
    )
    try:
        yield buf
    finally:
        structlog.contextvars.clear_contextvars()
        for h in logging.root.handlers[:]:
            logging.root.removeHandler(h)
        logging.basicConfig(force=True)


def _lines(buf: io.StringIO) -> list[dict]:
    return [json.loads(ln) for ln in buf.getvalue().splitlines() if ln.strip()]


class TestRecordNotMutated:
    """Regression: the old _ModuleFormatter rewrote record.msg / record.args,
    which corrupted every downstream handler (notably the Discord webhook)."""

    def test_message_and_args_survive_for_other_handlers(self, json_logs: io.StringIO) -> None:
        seen: list[logging.LogRecord] = []

        class Spy(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                seen.append(record)

        logging.root.addHandler(Spy())
        logging.getLogger("routers.timers").warning("[%s] saved", "cool_channel")

        assert len(seen) == 1
        assert seen[0].getMessage() == "[cool_channel] saved"
        assert seen[0].args is not None
        # and the '[' is not escaped
        assert "\\[" not in seen[0].getMessage()


class TestJsonSchema:
    def test_required_keys_present(self, json_logs: io.StringIO) -> None:
        logging.getLogger("routers.timers").info("hello")
        (line,) = _lines(json_logs)
        assert _REQUIRED_KEYS <= line.keys()
        assert line["event"] == "hello"
        assert line["level"] == "info"
        assert line["service"] == "api"
        assert line["mod"] == "timers"
        assert line["own"] is True

    def test_third_party_logger_same_schema_not_own(self, json_logs: io.StringIO) -> None:
        logging.getLogger("twitchio.websocket").warning("reconnecting")
        (line,) = _lines(json_logs)
        assert _REQUIRED_KEYS <= line.keys()
        assert line["own"] is False
        assert line["mod"] == "websocket"

    def test_cjk_not_escaped(self, json_logs: io.StringIO) -> None:
        logging.getLogger("routers.x").info("找不到這個計時器")
        assert "找不到這個計時器" in json_logs.getvalue()

    def test_extra_fields_passthrough(self, json_logs: io.StringIO) -> None:
        logging.getLogger("routers.x").warning(
            "request_failed", extra={"code": "TIMER.NOT_FOUND", "http_status": 404}
        )
        (line,) = _lines(json_logs)
        assert line["code"] == "TIMER.NOT_FOUND"
        assert line["http_status"] == 404

    def test_exc_info_rendered_as_exception_field(self, json_logs: io.StringIO) -> None:
        try:
            raise ValueError("boom")
        except ValueError:
            logging.getLogger("routers.x").exception("blew up")
        (line,) = _lines(json_logs)
        assert "exception" in line
        assert "ValueError: boom" in line["exception"]


class TestContextvars:
    def test_bound_context_appears(self, json_logs: io.StringIO) -> None:
        structlog.contextvars.bind_contextvars(request_id="rid-1", user_id="u-1")
        logging.getLogger("routers.x").info("with context")
        (line,) = _lines(json_logs)
        assert line["request_id"] == "rid-1"
        assert line["user_id"] == "u-1"

    def test_clear_prevents_leak_between_requests(self, json_logs: io.StringIO) -> None:
        structlog.contextvars.bind_contextvars(request_id="req-A", user_id="user-A")
        logging.getLogger("routers.x").info("first")
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id="req-B")
        logging.getLogger("routers.x").info("second")

        first, second = _lines(json_logs)
        assert first["user_id"] == "user-A"
        assert "user_id" not in second
        assert second["request_id"] == "req-B"


class TestConsoleMode:
    def test_console_mode_is_not_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", buf)
        setup_logging(service_name="api", console=True)
        try:
            logging.getLogger("routers.x").info("readable line")
            out = buf.getvalue()
            assert "readable line" in out
            with pytest.raises(json.JSONDecodeError):
                json.loads(out.splitlines()[0])
        finally:
            for h in logging.root.handlers[:]:
                logging.root.removeHandler(h)
            logging.basicConfig(force=True)
