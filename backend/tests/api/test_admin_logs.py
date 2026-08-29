"""Tests for the line -> LogRecordOut parsing in api.routers.admin.logs."""

from __future__ import annotations

import json
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-auth-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-test")

from routers.admin.logs import LogLine, _record_from_line, _to_records


def _line(text: str, stream: str = "stdout") -> LogLine:
    return LogLine(stream=stream, text=text)


TS = "2026-08-28T08:05:19.852626Z "


class TestRecordFromLine:
    def test_json_line(self):
        payload = {
            "event": "request_failed",
            "level": "error",
            "logger": "routers.timers_router",
            "mod": "timers_router",
            "own": True,
            "service": "api",
            "request_id": "abc123",
            "code": "TIMER.NOT_FOUND",
            "channel_id": "999",
            "http_status": 404,
            "timestamp": "2026-08-28T08:05:19Z",
        }
        rec = _record_from_line(_line(TS + json.dumps(payload)))
        assert rec.source == "json"
        assert rec.level == "ERROR"
        assert rec.message == "request_failed"
        assert rec.mod == "timers_router"
        assert rec.own is True
        assert rec.request_id == "abc123"
        assert rec.channel == "999"
        assert rec.code == "TIMER.NOT_FOUND"
        assert rec.extra == {"http_status": 404}
        assert rec.ts == "2026-08-28 08:05:19"

    def test_json_with_exception(self):
        payload = {"event": "boom", "level": "error", "exception": "Traceback...\nValueError: x"}
        rec = _record_from_line(_line(TS + json.dumps(payload)))
        assert rec.exception and "ValueError" in rec.exception

    def test_postgres_line_non_utc_timezone(self):
        raw = TS + "2026-05-15 01:39:23.531 CST [28] ERROR:  deadlock detected"
        rec = _record_from_line(_line(raw))
        assert rec.source == "postgres"
        assert rec.level == "ERROR"
        assert rec.pid == "28"
        assert rec.message == "deadlock detected"

    def test_raw_ansi_line_level_guessed(self):
        raw = TS + "\x1b[31mSomething ERROR happened\x1b[0m"
        rec = _record_from_line(_line(raw))
        assert rec.source == "raw"
        assert rec.level == "ERROR"

    def test_raw_line_no_docker_ts(self):
        rec = _record_from_line(_line("plain uvicorn startup line"))
        assert rec.source == "raw"
        assert rec.ts == ""
        assert rec.level == "UNKNOWN"

    def test_console_line_decoded_to_structured(self):
        # structlog ConsoleRenderer output (colours stripped for readability;
        # real lines carry ANSI which the parser removes).
        body = (
            "2026-08-29T21:22:03.697864Z [info     ] "
            "Will watch for changes in ['/app/api'] "
            "[routers.timers_router] mod=timers_router own=True "
            "request_id=abc-123 service=api"
        )
        rec = _record_from_line(_line(TS + body))
        assert rec.source == "console"
        assert rec.level == "INFO"
        assert rec.message == "Will watch for changes in ['/app/api']"
        assert rec.logger == "routers.timers_router"
        assert rec.mod == "timers_router"
        assert rec.own is True
        assert rec.request_id == "abc-123"
        assert rec.service == "api"

    def test_console_line_uvicorn_not_misread_as_error(self):
        # `mod=error` (logger name uvicorn.error) used to trip _guess_level.
        body = (
            "2026-08-29T21:22:03.698Z [info     ] Uvicorn running on http://0.0.0.0:8000 "
            "[uvicorn.error] "
            "color_message='Uvicorn running on http://%s (Press CTRL+C to quit)' "
            "mod=error own=False service=api"
        )
        rec = _record_from_line(_line(TS + body))
        assert rec.source == "console"
        assert rec.level == "INFO"
        assert rec.message == "Uvicorn running on http://0.0.0.0:8000"
        assert rec.extra["color_message"].startswith("Uvicorn running on http://%s")

    def test_console_line_ansi_stripped(self):
        body = (
            "\x1b[2m2026-08-29T21:22:03.700Z\x1b[0m [\x1b[31m\x1b[1merror    \x1b[0m] "
            "\x1b[1mboom\x1b[0m [\x1b[34mservices.x\x1b[0m] "
            "\x1b[36mmod\x1b[0m=\x1b[35mx\x1b[0m \x1b[36mown\x1b[0m=\x1b[35mTrue\x1b[0m "
            "\x1b[36mservice\x1b[0m=\x1b[35mapi\x1b[0m"
        )
        rec = _record_from_line(_line(TS + body))
        assert rec.source == "console"
        assert rec.level == "ERROR"
        assert rec.message == "boom"

    def test_non_pipeline_bracket_line_stays_raw(self):
        # An arbitrary line that happens to have a [dotted.token] but no kv tail.
        rec = _record_from_line(_line(TS + "2026-08-29T21:22:03.7Z [info] loaded [app.config] ok"))
        assert rec.source == "raw"

    def test_guess_level_ignores_key_value_error(self):
        rec = _record_from_line(_line(TS + "startup done  mod=error own=False service=x"))
        assert rec.source == "raw"
        assert rec.level == "UNKNOWN"

    def test_bad_json_falls_back_to_raw(self):
        rec = _record_from_line(_line(TS + '{"event": not valid json'))
        assert rec.source == "raw"


class TestToRecordsFiltering:
    def _lines(self):
        return [
            _line(TS + json.dumps({"event": "a", "level": "debug"})),
            _line(TS + json.dumps({"event": "b", "level": "info"})),
            _line(TS + json.dumps({"event": "c", "level": "warning"})),
            _line(TS + json.dumps({"event": "d", "level": "error"})),
            _line(TS + '    File "x.py", line 3, in foo'),  # traceback continuation
        ]

    def test_level_error_keeps_error_and_unknown(self):
        recs = _to_records(self._lines(), level="ERROR")
        events = [r.message for r in recs]
        assert "d" in events  # the error
        assert "a" not in events and "b" not in events and "c" not in events
        # the unrecognised traceback line is never filtered out
        assert any(r.source == "raw" and "File" in r.message for r in recs)

    def test_level_all_keeps_everything(self):
        assert len(_to_records(self._lines(), level="ALL")) == 5

    def test_q_substring_match(self):
        recs = _to_records(self._lines(), q="warning")
        # matches the raw json text of line c (contains "warning")
        assert any(r.message == "c" for r in recs)
