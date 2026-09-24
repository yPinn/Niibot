"""Unit tests for shared.cache — AsyncTTLCache and the @cached decorator."""

import asyncio
import time

import pytest

from shared.cache import _MISSING, AsyncTTLCache, cached

# ---------------------------------------------------------------------------
# AsyncTTLCache — synchronous operations
# ---------------------------------------------------------------------------


class TestAsyncTTLCacheBasic:
    def setup_method(self):
        self.cache = AsyncTTLCache(maxsize=10, ttl=60)

    def test_get_miss_returns_sentinel(self):
        assert self.cache.get("missing") is _MISSING

    def test_get_stale_miss_returns_sentinel(self):
        assert self.cache.get_stale("missing") is _MISSING

    def test_set_and_get_fresh(self):
        self.cache.set("k", "v")
        assert self.cache.get("k") == "v"

    def test_set_also_writes_stale(self):
        self.cache.set("k", "v")
        assert self.cache.get_stale("k") == "v"

    def test_set_overwrites_existing(self):
        self.cache.set("k", "first")
        self.cache.set("k", "second")
        assert self.cache.get("k") == "second"

    def test_invalidate_removes_fresh_keeps_stale(self):
        self.cache.set("k", "v")
        self.cache.invalidate("k")
        assert self.cache.get("k") is _MISSING
        assert self.cache.get_stale("k") == "v"

    def test_invalidate_missing_key_is_noop(self):
        self.cache.invalidate("nonexistent")  # must not raise

    def test_clear_removes_fresh_preserves_stale(self):
        self.cache.set("a", 1)
        self.cache.set("b", 2)
        self.cache.clear()
        assert self.cache.get("a") is _MISSING
        assert self.cache.get("b") is _MISSING
        assert self.cache.get_stale("a") == 1
        assert self.cache.get_stale("b") == 2

    def test_size_property(self):
        assert self.cache.size == 0
        self.cache.set("x", 1)
        assert self.cache.size == 1

    def test_stale_size_property(self):
        assert self.cache.stale_size == 0
        self.cache.set("x", 1)
        assert self.cache.stale_size == 1

    def test_cached_none_value_is_distinguishable(self):
        # None is a valid cached value — must not be confused with _MISSING
        self.cache.set("null_key", None)
        assert self.cache.get("null_key") is None
        assert self.cache.get("null_key") is not _MISSING


class TestAsyncTTLCacheTTL:
    def test_fresh_value_expires_after_ttl(self):
        cache = AsyncTTLCache(maxsize=10, ttl=0.05)  # 50 ms
        cache.set("k", "v")
        time.sleep(0.1)
        assert cache.get("k") is _MISSING

    def test_stale_value_survives_ttl_expiry(self):
        cache = AsyncTTLCache(maxsize=10, ttl=0.05)
        cache.set("k", "v")
        time.sleep(0.1)
        assert cache.get_stale("k") == "v"


class TestAsyncTTLCacheInvalidatePrefix:
    def setup_method(self):
        self.cache = AsyncTTLCache(maxsize=10, ttl=60)

    def test_removes_matching_keys(self):
        self.cache.set("redemption:ch1:foo", 1)
        self.cache.set("redemption:ch1:bar", 2)
        self.cache.invalidate_prefix("redemption:ch1:")
        assert self.cache.get("redemption:ch1:foo") is _MISSING
        assert self.cache.get("redemption:ch1:bar") is _MISSING

    def test_does_not_remove_non_matching_keys(self):
        self.cache.set("redemption:ch1:foo", 1)
        self.cache.set("redemption:ch2:baz", 3)
        self.cache.invalidate_prefix("redemption:ch1:")
        assert self.cache.get("redemption:ch2:baz") == 3

    def test_preserves_stale_for_invalidated_keys(self):
        self.cache.set("redemption:ch1:foo", 42)
        self.cache.invalidate_prefix("redemption:ch1:")
        assert self.cache.get("redemption:ch1:foo") is _MISSING
        assert self.cache.get_stale("redemption:ch1:foo") == 42

    def test_empty_prefix_removes_all_keys(self):
        self.cache.set("a", 1)
        self.cache.set("b", 2)
        self.cache.invalidate_prefix("")
        assert self.cache.get("a") is _MISSING
        assert self.cache.get("b") is _MISSING

    def test_no_match_is_noop(self):
        self.cache.set("other:ch1:x", 99)
        self.cache.invalidate_prefix("redemption:ch1:")  # no matches
        assert self.cache.get("other:ch1:x") == 99


class TestAsyncTTLCacheLRU:
    def test_oldest_stale_evicted_when_maxsize_exceeded(self):
        cache = AsyncTTLCache(maxsize=3, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)  # evicts "a"
        assert cache.get_stale("a") is _MISSING
        assert cache.get_stale("d") == 4

    def test_recently_accessed_stale_not_evicted(self):
        cache = AsyncTTLCache(maxsize=2, ttl=60)
        cache.set("a", 1)
        cache.set("b", 2)
        # Touch "a" to make it most-recently-used
        cache.get_stale("a")
        cache.set("c", 3)  # should evict "b", not "a"
        assert cache.get_stale("a") == 1
        assert cache.get_stale("b") is _MISSING
        assert cache.get_stale("c") == 3


# ---------------------------------------------------------------------------
# @cached decorator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCachedDecorator:
    async def test_result_is_cached_on_second_call(self):
        cache = AsyncTTLCache(maxsize=10, ttl=60)
        calls = 0

        @cached(cache=cache, key_func=lambda: "key")
        async def fetch():
            nonlocal calls
            calls += 1
            return "result"

        r1 = await fetch()
        r2 = await fetch()
        assert r1 == r2 == "result"
        assert calls == 1  # only called once

    async def test_retries_specified_number_of_times(self):
        cache = AsyncTTLCache(maxsize=10, ttl=60)
        calls = 0

        @cached(cache=cache, key_func=lambda: "fail", retry=3)
        async def always_fail():
            nonlocal calls
            calls += 1
            raise RuntimeError("DB down")

        with pytest.raises(RuntimeError):
            await always_fail()

        assert calls == 3

    async def test_returns_stale_when_all_retries_exhausted(self):
        cache = AsyncTTLCache(maxsize=10, ttl=0.05)

        @cached(cache=cache, key_func=lambda: "stale_key", retry=1)
        async def fetch():
            return "fresh"

        await fetch()  # primes the cache + stale store
        await asyncio.sleep(0.1)  # let TTL expire (fresh evicted, stale survives)
        assert cache.get("stale_key") is _MISSING

        @cached(cache=cache, key_func=lambda: "stale_key", retry=1)
        async def failing():
            raise RuntimeError("DB down")

        result = await failing()
        assert result == "fresh"

    async def test_cancelled_error_is_not_retried(self):
        cache = AsyncTTLCache(maxsize=10, ttl=60)
        calls = 0

        @cached(cache=cache, key_func=lambda: "cancel", retry=3)
        async def gets_cancelled():
            nonlocal calls
            calls += 1
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await gets_cancelled()

        assert calls == 1  # no retry on cancellation

    async def test_non_retryable_error_skips_retry_and_stale_fallback(self):
        class DeterministicDecodeError(ValueError):
            pass

        cache = AsyncTTLCache(maxsize=10, ttl=60)
        cache.set("credential", "old-value")
        cache.invalidate("credential")
        calls = 0

        @cached(
            cache=cache,
            key_func=lambda: "credential",
            retry=3,
            non_retryable=(DeterministicDecodeError,),
        )
        async def cannot_decode():
            nonlocal calls
            calls += 1
            raise DeterministicDecodeError("invalid envelope")

        with pytest.raises(DeterministicDecodeError, match="invalid envelope"):
            await cannot_decode()

        assert calls == 1

    async def test_different_keys_cached_independently(self):
        cache = AsyncTTLCache(maxsize=10, ttl=60)

        @cached(cache=cache, key_func=lambda k: f"key:{k}")
        async def fetch(k: str):
            return f"value:{k}"

        r1 = await fetch("a")
        r2 = await fetch("b")
        assert r1 == "value:a"
        assert r2 == "value:b"

    async def test_concurrent_calls_for_same_key_call_db_once(self):
        cache = AsyncTTLCache(maxsize=10, ttl=60)
        calls = 0

        @cached(cache=cache, key_func=lambda: "shared")
        async def slow_fetch():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.05)
            return "data"

        results = await asyncio.gather(slow_fetch(), slow_fetch(), slow_fetch())
        assert all(r == "data" for r in results)
        assert calls == 1  # lock prevents duplicate DB calls
