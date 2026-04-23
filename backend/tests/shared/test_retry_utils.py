"""Unit tests for shared.retry_utils."""

from __future__ import annotations

from unittest.mock import MagicMock

from shared.retry_utils import format_duration, parse_retry_after


class _ExcError(Exception):
    def __init__(self, **attrs):
        for k, v in attrs.items():
            setattr(self, k, v)


class TestFormatDuration:
    def test_zero(self):
        assert format_duration(0) == "0s"

    def test_seconds_only(self):
        assert format_duration(45) == "45s"

    def test_exactly_one_minute(self):
        assert format_duration(60) == "1m"

    def test_minutes_and_seconds(self):
        assert format_duration(90) == "1m30s"

    def test_exactly_one_hour(self):
        assert format_duration(3600) == "1h"

    def test_hours_and_minutes(self):
        assert format_duration(3660) == "1h1m"

    def test_hours_without_minutes(self):
        assert format_duration(7200) == "2h"

    def test_float_is_truncated(self):
        assert format_duration(90.9) == "1m30s"


class TestParseRetryAfter:
    def test_retry_after_attribute_used(self):
        exc = _ExcError(retry_after=30.0)
        assert parse_retry_after(exc) == 30.0

    def test_retry_after_zero_falls_to_fallback(self):
        exc = _ExcError(retry_after=0)
        assert parse_retry_after(exc, fallback=5.0) == 5.0

    def test_retry_after_negative_falls_to_fallback(self):
        exc = _ExcError(retry_after=-1.0)
        assert parse_retry_after(exc, fallback=5.0) == 5.0

    def test_retry_after_invalid_string_falls_to_fallback(self):
        exc = _ExcError(retry_after="not-a-number")
        assert parse_retry_after(exc, fallback=5.0) == 5.0

    def test_retry_after_none_falls_to_fallback(self):
        exc = _ExcError(retry_after=None)
        assert parse_retry_after(exc, fallback=5.0) == 5.0

    def test_header_retry_after_used(self):
        resp = MagicMock()
        resp.headers = {"Retry-After": "10"}
        exc = _ExcError(response=resp)
        assert parse_retry_after(exc) == 10.0

    def test_header_lowercase_used(self):
        resp = MagicMock()
        resp.headers = {"retry-after": "20"}
        exc = _ExcError(response=resp)
        assert parse_retry_after(exc) == 20.0

    def test_header_underscore_used(self):
        resp = MagicMock()
        resp.headers = {"retry_after": "15"}
        exc = _ExcError(response=resp)
        assert parse_retry_after(exc) == 15.0

    def test_header_invalid_value_falls_to_fallback(self):
        resp = MagicMock()
        resp.headers = {"Retry-After": "bad"}
        exc = _ExcError(response=resp)
        assert parse_retry_after(exc, fallback=7.0) == 7.0

    def test_no_attrs_uses_fallback(self):
        assert parse_retry_after(Exception(), fallback=3.0) == 3.0

    def test_default_fallback_is_five(self):
        assert parse_retry_after(Exception()) == 5.0
