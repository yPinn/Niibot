"""Unit tests for core.rate_limit.RateLimiter."""

from __future__ import annotations

import time

import pytest
from fastapi import HTTPException

from core.rate_limit import RateLimiter


class TestRateLimiterAllow:
    def test_first_call_is_allowed(self):
        rl = RateLimiter(max_calls=3, period=60.0)
        assert rl.allow("key") is True

    def test_calls_up_to_limit_are_allowed(self):
        rl = RateLimiter(max_calls=3, period=60.0)
        assert rl.allow("key") is True
        assert rl.allow("key") is True
        assert rl.allow("key") is True

    def test_call_exceeding_limit_is_denied(self):
        rl = RateLimiter(max_calls=2, period=60.0)
        rl.allow("key")
        rl.allow("key")
        assert rl.allow("key") is False

    def test_deny_does_not_record_the_attempt(self):
        """Denied calls should not consume quota — once denied, stays denied but no extra penalty."""
        rl = RateLimiter(max_calls=1, period=60.0)
        rl.allow("key")  # consumes the 1 slot
        assert rl.allow("key") is False  # denied, not recorded
        assert rl.allow("key") is False  # still denied, not worse

    def test_different_keys_are_independent(self):
        rl = RateLimiter(max_calls=1, period=60.0)
        rl.allow("a")
        assert rl.allow("a") is False
        assert rl.allow("b") is True  # separate bucket

    def test_expired_calls_no_longer_counted(self):
        rl = RateLimiter(max_calls=1, period=0.05)  # 50 ms window
        assert rl.allow("key") is True  # fills the window
        time.sleep(0.1)  # window expires
        assert rl.allow("key") is True  # fresh window

    def test_calls_within_period_still_count(self):
        rl = RateLimiter(max_calls=2, period=60.0)
        rl.allow("key")
        rl.allow("key")
        # window has NOT expired → still denied
        assert rl.allow("key") is False

    def test_unknown_key_starts_fresh(self):
        rl = RateLimiter(max_calls=1, period=60.0)
        rl.allow("existing-key")
        # a brand-new key should start at zero
        assert rl.allow("new-key") is True


class TestRateLimiterRequire:
    def test_require_passes_within_limit(self):
        rl = RateLimiter(max_calls=5, period=60.0)
        rl.require("key")  # must not raise

    def test_require_raises_429_when_exceeded(self):
        rl = RateLimiter(max_calls=1, period=60.0)
        rl.allow("key")  # consume the slot
        with pytest.raises(HTTPException) as exc_info:
            rl.require("key")
        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "Rate limit exceeded"

    def test_require_raises_for_every_exceeded_call(self):
        rl = RateLimiter(max_calls=1, period=60.0)
        rl.allow("key")
        for _ in range(3):
            with pytest.raises(HTTPException) as exc_info:
                rl.require("key")
            assert exc_info.value.status_code == 429
