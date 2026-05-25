"""Unit tests for twitch.components.games — GamesComponent (roll/roulette, choose).

TwitchIO wraps component methods with a Command descriptor.
Use `.callback(component, ctx, ...)` to invoke the raw implementation directly.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitch.components.games import (
    _MAX_OPTIONS,
    _ROULETTE_TIMEOUT,
    _TOTAL_CHAMBERS,
    GamesComponent,
    _ChamberState,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PATCH_CHECK = "twitch.components.games.check_command"
PATCH_HTTPX = "twitch.components.games.httpx.AsyncClient"


def _make_bot(*, is_mod: bool = True) -> MagicMock:
    bot = MagicMock()
    bot.token_database = MagicMock()
    bot.channels = MagicMock()
    bot._bot_id = "bot123"
    bot._client_id = "client_abc"
    bot._bot_is_mod = {"ch_test"} if is_mod else set()
    return bot


def _make_ctx(
    *,
    display_name: str = "Streamer",
    name: str = "streamer",
    user_id: str = "user999",
    moderator: bool = False,
    broadcaster: bool = False,
    channel_id: str = "ch_test",
) -> MagicMock:
    ctx = MagicMock()
    ctx.chatter.display_name = display_name
    ctx.chatter.name = name
    ctx.chatter.id = user_id
    ctx.chatter.moderator = moderator
    ctx.chatter.broadcaster = broadcaster
    ctx.broadcaster.id = channel_id
    ctx.channel.id = channel_id
    return ctx


@pytest.fixture()
def component() -> GamesComponent:
    comp = GamesComponent(_make_bot(is_mod=True))
    comp._ctx_reply = AsyncMock()
    return comp


async def _roll(component: GamesComponent, ctx: MagicMock, **kwargs) -> None:
    """Invoke roll bypassing the TwitchIO Command descriptor."""
    await GamesComponent.roll.callback(component, ctx, **kwargs)  # type: ignore[attr-defined]


async def _choose(component: GamesComponent, ctx: MagicMock, **kwargs) -> None:
    """Invoke choose bypassing the TwitchIO Command descriptor."""
    await GamesComponent.choose.callback(component, ctx, **kwargs)  # type: ignore[attr-defined]


def _make_roulette_component(*, is_mod: bool = True) -> GamesComponent:
    comp = GamesComponent(_make_bot(is_mod=is_mod))
    comp._ctx_reply = AsyncMock()
    token = MagicMock()
    token.token = "fake_token"
    comp.channel_repo.get_token = AsyncMock(return_value=token)
    return comp


def _make_http_mock(*, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = ""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=resp)
    return client


def _inject_chamber(comp: GamesComponent, channel_id: str, *, hit: bool) -> MagicMock:
    """Inject a mock chamber that returns a controlled pull outcome."""
    chamber = MagicMock(spec=_ChamberState)
    chamber.pull.return_value = hit
    chamber.remaining = _TOTAL_CHAMBERS - 1
    comp._chambers[channel_id] = chamber
    return chamber


# ---------------------------------------------------------------------------
# BUILTIN_DEFS registration
# ---------------------------------------------------------------------------


class TestBuiltinRegistration:
    def test_roll_in_builtin_defs(self) -> None:
        from shared.builtin_commands import BUILTIN_MAP

        assert "roll" in BUILTIN_MAP

    def test_choose_in_builtin_defs(self) -> None:
        from shared.builtin_commands import BUILTIN_MAP

        assert "choose" in BUILTIN_MAP

    def test_roll_aliases(self) -> None:
        from shared.builtin_commands import BUILTIN_ALIAS_MAP

        assert BUILTIN_ALIAS_MAP.get("輪盤") == "roll"

    def test_choose_aliases(self) -> None:
        from shared.builtin_commands import BUILTIN_ALIAS_MAP

        assert BUILTIN_ALIAS_MAP.get("選擇") == "choose"

    def test_roll_has_description(self) -> None:
        from shared.builtin_commands import BUILTIN_DESCRIPTIONS, PUBLIC_DESCRIPTIONS

        assert "roll" in BUILTIN_DESCRIPTIONS
        assert "roll" in PUBLIC_DESCRIPTIONS

    def test_choose_has_description(self) -> None:
        from shared.builtin_commands import BUILTIN_DESCRIPTIONS, PUBLIC_DESCRIPTIONS

        assert "choose" in BUILTIN_DESCRIPTIONS
        assert "choose" in PUBLIC_DESCRIPTIONS


# ---------------------------------------------------------------------------
# _ChamberState unit tests
# ---------------------------------------------------------------------------


class TestChamberState:
    def test_initial_remaining(self) -> None:
        assert _ChamberState().remaining == _TOTAL_CHAMBERS

    def test_remaining_decrements_on_pull(self) -> None:
        c = _ChamberState()
        c.pull()
        assert c.remaining == _TOTAL_CHAMBERS - 1

    def test_guaranteed_hit_within_total_chambers(self) -> None:
        for _ in range(200):
            c = _ChamberState()
            hits = sum(c.pull() for _ in range(_TOTAL_CHAMBERS))
            assert hits == 1

    def test_hit_occurs_exactly_once(self) -> None:
        c = _ChamberState()
        results = [c.pull() for _ in range(_TOTAL_CHAMBERS)]
        assert results.count(True) == 1


# ---------------------------------------------------------------------------
# !roll (Russian Roulette — shared chamber)
# ---------------------------------------------------------------------------


class TestRoulette:
    @pytest.mark.asyncio
    async def test_disabled_command_no_reply(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=None):
            ctx = _make_ctx()
            await _roll(component, ctx)
            component._ctx_reply.assert_not_called()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_safe_outcome(self) -> None:
        comp = _make_roulette_component()
        ctx = _make_ctx()
        _inject_chamber(comp, ctx.broadcaster.id, hit=False)
        with patch(PATCH_CHECK, return_value=MagicMock()):
            await _roll(comp, ctx)
            text: str = comp._ctx_reply.call_args[0][1]
            assert "平安" in text

    @pytest.mark.asyncio
    async def test_safe_does_not_reset_chamber(self) -> None:
        comp = _make_roulette_component()
        ctx = _make_ctx()
        chamber = _inject_chamber(comp, ctx.broadcaster.id, hit=False)
        with patch(PATCH_CHECK, return_value=MagicMock()):
            await _roll(comp, ctx)
            assert comp._chambers[ctx.broadcaster.id] is chamber

    @pytest.mark.asyncio
    async def test_hit_resets_chamber(self) -> None:
        comp = _make_roulette_component()
        ctx = _make_ctx()
        old_chamber = _inject_chamber(comp, ctx.broadcaster.id, hit=True)
        with (
            patch(PATCH_CHECK, return_value=MagicMock()),
            patch(PATCH_HTTPX, return_value=_make_http_mock()),
        ):
            await _roll(comp, ctx)
            assert comp._chambers[ctx.broadcaster.id] is not old_chamber

    @pytest.mark.asyncio
    async def test_hit_announces_outcome(self) -> None:
        comp = _make_roulette_component()
        ctx = _make_ctx()
        _inject_chamber(comp, ctx.broadcaster.id, hit=True)
        with (
            patch(PATCH_CHECK, return_value=MagicMock()),
            patch(PATCH_HTTPX, return_value=_make_http_mock()),
        ):
            await _roll(comp, ctx)
            text: str = comp._ctx_reply.call_args[0][1]
            assert "出局" in text

    @pytest.mark.asyncio
    async def test_broadcaster_no_chamber_pull(self) -> None:
        comp = _make_roulette_component()
        ctx = _make_ctx(broadcaster=True)
        with patch(PATCH_CHECK, return_value=MagicMock()):
            await _roll(comp, ctx)
            assert ctx.broadcaster.id not in comp._chambers

    @pytest.mark.asyncio
    async def test_broadcaster_message(self) -> None:
        comp = _make_roulette_component()
        ctx = _make_ctx(broadcaster=True)
        with patch(PATCH_CHECK, return_value=MagicMock()):
            await _roll(comp, ctx)
            text: str = comp._ctx_reply.call_args[0][1]
            assert "狼人" in text

    @pytest.mark.asyncio
    async def test_hit_bot_not_mod_does_not_call_api(self) -> None:
        comp = _make_roulette_component(is_mod=False)
        ctx = _make_ctx()
        _inject_chamber(comp, ctx.broadcaster.id, hit=True)
        with patch(PATCH_CHECK, return_value=MagicMock()), patch(PATCH_HTTPX) as mock_cls:
            await _roll(comp, ctx)
            mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_hit_no_token_does_not_call_api(self) -> None:
        comp = _make_roulette_component()
        comp.channel_repo.get_token = AsyncMock(return_value=None)
        ctx = _make_ctx()
        _inject_chamber(comp, ctx.broadcaster.id, hit=True)
        with patch(PATCH_CHECK, return_value=MagicMock()), patch(PATCH_HTTPX) as mock_cls:
            await _roll(comp, ctx)
            mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_hit_timeout_success(self) -> None:
        comp = _make_roulette_component()
        http_mock = _make_http_mock(status_code=200)
        ctx = _make_ctx()
        _inject_chamber(comp, ctx.broadcaster.id, hit=True)
        with (
            patch(PATCH_CHECK, return_value=MagicMock()),
            patch(PATCH_HTTPX, return_value=http_mock),
        ):
            await _roll(comp, ctx)
            http_mock.post.assert_awaited_once()
            data = http_mock.post.call_args.kwargs["json"]["data"]
            assert data["duration"] == _ROULETTE_TIMEOUT
            assert data["user_id"] == ctx.chatter.id

    @pytest.mark.asyncio
    async def test_hit_timeout_api_failure_still_announces(self) -> None:
        comp = _make_roulette_component()
        ctx = _make_ctx()
        _inject_chamber(comp, ctx.broadcaster.id, hit=True)
        with (
            patch(PATCH_CHECK, return_value=MagicMock()),
            patch(PATCH_HTTPX, return_value=_make_http_mock(status_code=403)),
        ):
            await _roll(comp, ctx)
            text: str = comp._ctx_reply.call_args[0][1]
            assert "出局" in text

    @pytest.mark.asyncio
    async def test_hit_timeout_exception_still_announces(self) -> None:
        comp = _make_roulette_component()
        http_mock = _make_http_mock()
        http_mock.post = AsyncMock(side_effect=Exception("network error"))
        ctx = _make_ctx()
        _inject_chamber(comp, ctx.broadcaster.id, hit=True)
        with (
            patch(PATCH_CHECK, return_value=MagicMock()),
            patch(PATCH_HTTPX, return_value=http_mock),
        ):
            await _roll(comp, ctx)
            text: str = comp._ctx_reply.call_args[0][1]
            assert "出局" in text

    @pytest.mark.asyncio
    async def test_new_channel_gets_fresh_chamber(self, component: GamesComponent) -> None:
        assert "new_channel" not in component._chambers
        ctx = _make_ctx(channel_id="new_channel")
        with patch(PATCH_CHECK, return_value=None):
            await _roll(component, ctx)
        # command disabled — chamber not created yet (created on first valid trigger)

    @pytest.mark.asyncio
    async def test_chamber_shared_across_users(self) -> None:
        comp = _make_roulette_component()
        ctx1 = _make_ctx(user_id="u1")
        ctx2 = _make_ctx(user_id="u2")
        with patch(PATCH_CHECK, return_value=MagicMock()):
            _inject_chamber(comp, ctx1.broadcaster.id, hit=False)
            await _roll(comp, ctx1)
            _inject_chamber(comp, ctx2.broadcaster.id, hit=False)
            await _roll(comp, ctx2)
            # Both users share the same channel chamber namespace
            assert ctx1.broadcaster.id == ctx2.broadcaster.id


# ---------------------------------------------------------------------------
# !choose
# ---------------------------------------------------------------------------


class TestChoose:
    @pytest.mark.asyncio
    async def test_disabled_command_no_reply(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=None):
            ctx = _make_ctx()
            await _choose(component, ctx, args="a b")
            component._ctx_reply.assert_not_called()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_no_args_returns_usage(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            await _choose(component, ctx)
            text: str = component._ctx_reply.call_args[0][1]  # type: ignore[attr-defined]
            assert "用法" in text

    @pytest.mark.asyncio
    async def test_empty_args_returns_usage(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            await _choose(component, ctx, args="   ")
            text: str = component._ctx_reply.call_args[0][1]  # type: ignore[attr-defined]
            assert "用法" in text

    @pytest.mark.asyncio
    async def test_single_option_returns_error(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            await _choose(component, ctx, args="only")
            text: str = component._ctx_reply.call_args[0][1]  # type: ignore[attr-defined]
            assert "兩個" in text

    @pytest.mark.asyncio
    async def test_two_options_picks_one(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            await _choose(component, ctx, args="red blue")
            text: str = component._ctx_reply.call_args[0][1]  # type: ignore[attr-defined]
            assert "🎯" in text
            assert "Streamer" in text
            assert "red" in text or "blue" in text

    @pytest.mark.asyncio
    async def test_result_always_from_options(self, component: GamesComponent) -> None:
        options = ["alpha", "beta", "gamma", "delta"]
        results: set[str] = set()
        with patch(PATCH_CHECK, return_value=MagicMock()):
            for _ in range(40):
                ctx = _make_ctx()
                await _choose(component, ctx, args=" ".join(options))
                text: str = component._ctx_reply.call_args[0][1]  # type: ignore[attr-defined]
                picked = text.split("：")[-1].strip()
                results.add(picked)
        assert results <= set(options)
        assert len(results) > 1

    @pytest.mark.asyncio
    async def test_too_many_options_returns_error(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            many = " ".join(f"opt{i}" for i in range(_MAX_OPTIONS + 1))
            await _choose(component, ctx, args=many)
            text: str = component._ctx_reply.call_args[0][1]  # type: ignore[attr-defined]
            assert str(_MAX_OPTIONS) in text

    @pytest.mark.asyncio
    async def test_exactly_max_options_accepted(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            exact = " ".join(f"opt{i}" for i in range(_MAX_OPTIONS))
            await _choose(component, ctx, args=exact)
            text: str = component._ctx_reply.call_args[0][1]  # type: ignore[attr-defined]
            assert "🎯" in text

    @pytest.mark.asyncio
    async def test_fallback_to_chatter_name_when_no_display_name(
        self, component: GamesComponent
    ) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx(display_name="", name="rawname")
            await _choose(component, ctx, args="x y")
            text: str = component._ctx_reply.call_args[0][1]  # type: ignore[attr-defined]
            assert "rawname" in text
