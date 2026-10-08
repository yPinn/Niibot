"""Rate-limit snapshot registry and the snapshot providers registered into it."""

from __future__ import annotations

import time
from collections.abc import Iterator

import httpx
import pytest

from shared import rate_limits
from shared.http_egress import HostEgressClient
from shared.twitch_egress import TwitchEgressCoordinator


@pytest.fixture(autouse=True)
def _isolated_registry() -> Iterator[None]:
    saved = dict(rate_limits._providers)
    rate_limits._providers.clear()
    yield
    rate_limits._providers.clear()
    rate_limits._providers.update(saved)


def _entry(name: str, group: rate_limits.RateLimitGroup) -> rate_limits.RateLimitSnapshot:
    return {"name": name, "group": group, "limit": 1, "window_seconds": 1.0, "used": 0, "keys": 0}


class TestRegistry:
    def test_collects_every_provider_sorted_by_group_then_name(self) -> None:
        rate_limits.register("b", lambda: [_entry("z", "twitch"), _entry("a", "twitch")])
        rate_limits.register("a", lambda: [_entry("m", "inbound")])
        names = [s["name"] for s in rate_limits.collect_rate_limits()]
        assert names == ["m", "a", "z"]

    def test_failing_provider_is_skipped(self) -> None:
        def broken() -> list[rate_limits.RateLimitSnapshot]:
            raise RuntimeError("boom")

        rate_limits.register("broken", broken)
        rate_limits.register("ok", lambda: [_entry("ok", "inbound")])
        assert [s["name"] for s in rate_limits.collect_rate_limits()] == ["ok"]

    def test_register_replaces_and_unregister_removes(self) -> None:
        rate_limits.register("k", lambda: [_entry("old", "inbound")])
        rate_limits.register("k", lambda: [_entry("new", "inbound")])
        assert [s["name"] for s in rate_limits.collect_rate_limits()] == ["new"]
        rate_limits.unregister("k")
        assert rate_limits.collect_rate_limits() == []


class TestTwitchEgressSnapshots:
    @pytest.mark.asyncio
    async def test_reports_helix_usage_and_the_tightest_live_budget(self) -> None:
        egress = TwitchEgressCoordinator(helix_limit=10, helix_window=60.0, name="api")
        try:
            await egress.acquire_helix("app")
            await egress.acquire_helix("app")
            reset = str(time.time() + 30)
            egress.observe_helix(
                "app",
                status_code=200,
                headers={
                    "Ratelimit-Limit": "800",
                    "Ratelimit-Remaining": "700",
                    "Ratelimit-Reset": reset,
                },
            )
            egress.observe_helix(
                "token:abc",
                status_code=429,
                headers={
                    "Ratelimit-Limit": "800",
                    "Ratelimit-Remaining": "0",
                    "Ratelimit-Reset": reset,
                },
            )
            (helix,) = rate_limits.collect_rate_limits()
            assert helix["name"] == "api.helix"
            assert helix["used"] == 2
            assert helix["limit"] == 10
            assert helix["rejected"] == 1
            assert helix["provider"] == {"limit": 800, "remaining": 0, "reset_at": float(reset)}
            assert helix["blocked_seconds"] > 0
        finally:
            await egress.close()
        assert rate_limits.collect_rate_limits() == []

    @pytest.mark.asyncio
    async def test_expired_budget_is_not_reported(self) -> None:
        egress = TwitchEgressCoordinator(name="bot")
        try:
            egress.observe_helix(
                "app",
                status_code=200,
                headers={"Ratelimit-Remaining": "5", "Ratelimit-Reset": str(time.time() - 1)},
            )
            assert egress.snapshots()[0]["provider"] is None
        finally:
            await egress.close()

    @pytest.mark.asyncio
    async def test_chat_gates_appear_once_used(self) -> None:
        egress = TwitchEgressCoordinator(name="bot")
        try:
            assert [s["name"] for s in egress.snapshots()] == ["bot.helix"]
            await egress.acquire_chat("sender", "channel")
            assert [s["name"] for s in egress.snapshots()] == [
                "bot.helix",
                "bot.chat_sender",
                "bot.chat_channel",
            ]
        finally:
            await egress.close()

    def test_unnamed_coordinator_is_not_registered(self) -> None:
        TwitchEgressCoordinator()
        assert rate_limits.collect_rate_limits() == []


class TestHostEgressSnapshots:
    @pytest.mark.asyncio
    async def test_throttling_host_gets_its_own_entry(self) -> None:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(429 if request.url.host == "slow.test" else 200)
        )
        client = HostEgressClient(httpx.AsyncClient(transport=transport), name="preview")
        try:
            await client.get("https://ok.test/")
            await client.post("https://slow.test/")
            entries = {s["name"]: s for s in rate_limits.collect_rate_limits()}
            assert entries["preview.hosts"]["used"] == 2
            assert entries["preview.slow.test"]["rejected"] == 1
            assert "preview.ok.test" not in entries
        finally:
            await client.aclose()
        assert rate_limits.collect_rate_limits() == []
