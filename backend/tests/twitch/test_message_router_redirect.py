"""Unit tests for custom command redirect resolution in _MessageRouterMixin.

A custom_response beginning with "!" is a redirect. These tests cover the loop
that resolves a redirect to another *custom* command — the shape an imported
Nightbot alias takes — plus the loop and depth guards that keep a bad chain
from spinning the router.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitch.core._message_router_mixin import _MAX_REDIRECT_DEPTH, _MessageRouterMixin

from shared.models.command_config import CommandConfig

CHANNEL_ID = "123"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_config(name: str, response: str, *, command_type: str = "custom") -> CommandConfig:
    return CommandConfig(
        id=1,
        channel_id=CHANNEL_ID,
        command_name=name,
        command_type=command_type,
        enabled=True,
        custom_response=response,
        cooldown=0,
        min_role="everyone",
        usage_count=0,
    )


def make_payload(text: str):
    payload = MagicMock()
    # MagicMock(name=...) names the mock itself, so `name` must be set after construction.
    payload.broadcaster = MagicMock(id=CHANNEL_ID)
    payload.broadcaster.name = "streamer"
    payload.chatter = MagicMock(display_name="Nii")
    payload.chatter.name = "nii"
    payload.text = text
    payload.id = "msg-001"
    payload.broadcaster.send_message = AsyncMock()
    return payload


class _Router(_MessageRouterMixin):
    """Bare mixin host with only the attributes the handler touches."""

    def __init__(self, configs: dict[str, CommandConfig]) -> None:
        self._background_tasks = set()
        self.bot_id = "bot-001"
        self._configs = configs

        self.command_configs = MagicMock()
        self.command_configs.find_by_name_or_alias = AsyncMock(side_effect=self._lookup)
        self.command_configs.increment_usage_count = AsyncMock()

        self.channels = MagicMock()
        self.channels.get_channel = AsyncMock(return_value=None)

        self.sessions = MagicMock()
        self.sessions.session_id = MagicMock(return_value=None)
        self.analytics = MagicMock()

    async def _lookup(self, channel_id: str, name: str) -> CommandConfig | None:
        return self._configs.get(name)


@pytest.fixture(autouse=True)
def no_cooldowns():
    """Redirect behaviour is the subject here — keep cooldown state out of it."""
    with (
        patch("twitch.core._message_router_mixin.is_on_cooldown", return_value=False),
        patch("twitch.core._message_router_mixin.record_cooldown"),
    ):
        yield


# ---------------------------------------------------------------------------
# Redirect to another custom command
# ---------------------------------------------------------------------------


class TestCustomToCustomRedirect:
    @pytest.mark.asyncio
    async def test_redirect_reaches_a_custom_command(self):
        router = _Router(
            {
                "scores": make_config("scores", "!moontaku"),
                "moontaku": make_config("moontaku", "目前戰績 10-0"),
            }
        )
        payload = make_payload("!scores")

        handled = await router._handle_custom_command(payload)

        assert handled is True
        payload.broadcaster.send_message.assert_awaited_once()
        assert payload.broadcaster.send_message.await_args.kwargs["message"] == "目前戰績 10-0"

    @pytest.mark.asyncio
    async def test_redirect_forwards_query(self):
        router = _Router(
            {
                "pcspecs": make_config("pcspecs", "!specs $(query)"),
                "specs": make_config("specs", "規格：$(query)"),
            }
        )
        payload = make_payload("!pcspecs gpu")

        handled = await router._handle_custom_command(payload)

        assert handled is True
        assert payload.broadcaster.send_message.await_args.kwargs["message"] == "規格：gpu"

    @pytest.mark.asyncio
    async def test_redirect_with_fixed_arguments(self):
        # Nightbot alias shape: the alias carries arguments for its target.
        router = _Router(
            {
                "setmulti": make_config("setmulti", "!multi twitch.tv/nii"),
                "multi": make_config("multi", "多重視角：$(query)"),
            }
        )
        payload = make_payload("!setmulti")

        handled = await router._handle_custom_command(payload)

        assert handled is True
        assert (
            payload.broadcaster.send_message.await_args.kwargs["message"]
            == "多重視角：twitch.tv/nii"
        )

    @pytest.mark.asyncio
    async def test_usage_counted_for_every_hop(self):
        router = _Router(
            {
                "a": make_config("a", "!b"),
                "b": make_config("b", "done"),
            }
        )

        await router._handle_custom_command(make_payload("!a"))

        counted = [c.args[1] for c in router.command_configs.increment_usage_count.call_args_list]
        assert counted == ["a", "b"]


# ---------------------------------------------------------------------------
# Falling through to the builtin pipeline
# ---------------------------------------------------------------------------


class TestBuiltinFallthrough:
    @pytest.mark.asyncio
    async def test_redirect_to_builtin_falls_through_with_rewritten_text(self):
        router = _Router({"推": make_config("推", "!so $(query)")})
        payload = make_payload("!推 someone")

        handled = await router._handle_custom_command(payload)

        assert handled is False
        assert payload.text == "!so someone"
        payload.broadcaster.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_command_falls_through_untouched(self):
        router = _Router({})
        payload = make_payload("!whatever")

        assert await router._handle_custom_command(payload) is False
        assert payload.text == "!whatever"

    @pytest.mark.asyncio
    async def test_non_command_message_ignored(self):
        router = _Router({"a": make_config("a", "hi")})
        payload = make_payload("just chatting")

        assert await router._handle_custom_command(payload) is False


# ---------------------------------------------------------------------------
# Loop and depth guards
# ---------------------------------------------------------------------------


class TestRedirectGuards:
    @pytest.mark.asyncio
    async def test_self_referencing_redirect_is_dropped(self):
        router = _Router({"a": make_config("a", "!a")})
        payload = make_payload("!a")

        handled = await router._handle_custom_command(payload)

        assert handled is True
        payload.broadcaster.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mutual_redirect_is_dropped(self):
        router = _Router(
            {
                "a": make_config("a", "!b"),
                "b": make_config("b", "!a"),
            }
        )
        payload = make_payload("!a")

        handled = await router._handle_custom_command(payload)

        assert handled is True
        payload.broadcaster.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_chain_longer_than_the_limit_is_dropped(self):
        # a -> b -> c -> d -> e is 4 hops, one past _MAX_REDIRECT_DEPTH == 3.
        names = ["a", "b", "c", "d", "e"]
        configs = {n: make_config(n, f"!{nxt}") for n, nxt in zip(names, names[1:], strict=False)}
        configs["e"] = make_config("e", "終點")
        router = _Router(configs)
        payload = make_payload("!a")

        handled = await router._handle_custom_command(payload)

        assert _MAX_REDIRECT_DEPTH == 3
        assert handled is True
        payload.broadcaster.send_message.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_chain_at_the_limit_still_responds(self):
        names = ["a", "b", "c", "d"]
        configs = {n: make_config(n, f"!{nxt}") for n, nxt in zip(names, names[1:], strict=False)}
        configs["d"] = make_config("d", "終點")
        router = _Router(configs)
        payload = make_payload("!a")

        handled = await router._handle_custom_command(payload)

        assert handled is True
        assert payload.broadcaster.send_message.await_args.kwargs["message"] == "終點"
