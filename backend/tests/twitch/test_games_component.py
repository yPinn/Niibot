"""Unit tests for twitch.components.games — GamesComponent (roll, choose).

TwitchIO wraps component methods with a Command descriptor.
Use `.callback(component, ctx, ...)` to invoke the raw implementation directly.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitch.components.games import _MAX_OPTIONS, _MAX_SIDES, GamesComponent

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PATCH_CHECK = "twitch.components.games.check_command"


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.token_database = MagicMock()
    bot.channels = MagicMock()
    return bot


def _make_ctx(*, display_name: str = "Streamer", name: str = "streamer") -> MagicMock:
    ctx = MagicMock()
    ctx.chatter.display_name = display_name
    ctx.chatter.name = name
    ctx.channel.id = "ch_test"
    ctx.reply = AsyncMock()
    return ctx


@pytest.fixture()
def component() -> GamesComponent:
    return GamesComponent(_make_bot())


async def _roll(component: GamesComponent, ctx: MagicMock, **kwargs) -> None:
    """Invoke roll bypassing the TwitchIO Command descriptor."""
    await GamesComponent.roll.callback(component, ctx, **kwargs)  # type: ignore[attr-defined]


async def _choose(component: GamesComponent, ctx: MagicMock, **kwargs) -> None:
    """Invoke choose bypassing the TwitchIO Command descriptor."""
    await GamesComponent.choose.callback(component, ctx, **kwargs)  # type: ignore[attr-defined]


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

        assert BUILTIN_ALIAS_MAP.get("骰子") == "roll"

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
# !roll
# ---------------------------------------------------------------------------


class TestRoll:
    @pytest.mark.asyncio
    async def test_disabled_command_no_reply(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=None):
            ctx = _make_ctx()
            await _roll(component, ctx)
            ctx.reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_default_d6_output(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            await _roll(component, ctx)
            text: str = ctx.reply.call_args[0][0]
            assert "🎲" in text
            assert "d6" in text
            assert "Streamer" in text

    @pytest.mark.asyncio
    async def test_custom_sides(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            await _roll(component, ctx, args="20")
            text: str = ctx.reply.call_args[0][0]
            assert "d20" in text

    @pytest.mark.asyncio
    async def test_result_in_range(self, component: GamesComponent) -> None:
        results: set[int] = set()
        with patch(PATCH_CHECK, return_value=MagicMock()):
            for _ in range(50):
                ctx = _make_ctx()
                await _roll(component, ctx, args="6")
                text: str = ctx.reply.call_args[0][0]
                num = int(text.split("：")[-1])
                results.add(num)
        assert results <= set(range(1, 7))
        assert len(results) > 1

    @pytest.mark.asyncio
    async def test_sides_below_minimum_returns_error(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            await _roll(component, ctx, args="1")
            text: str = ctx.reply.call_args[0][0]
            assert "至少" in text

    @pytest.mark.asyncio
    async def test_sides_above_maximum_returns_error(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            await _roll(component, ctx, args=str(_MAX_SIDES + 1))
            text: str = ctx.reply.call_args[0][0]
            assert str(_MAX_SIDES) in text

    @pytest.mark.asyncio
    async def test_sides_at_maximum_accepted(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            await _roll(component, ctx, args=str(_MAX_SIDES))
            text: str = ctx.reply.call_args[0][0]
            assert "🎲" in text

    @pytest.mark.asyncio
    async def test_non_numeric_arg_defaults_to_d6(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            await _roll(component, ctx, args="abc")
            text: str = ctx.reply.call_args[0][0]
            assert "d6" in text

    @pytest.mark.asyncio
    async def test_extra_args_only_first_token_parsed(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            await _roll(component, ctx, args="12 garbage")
            text: str = ctx.reply.call_args[0][0]
            assert "d12" in text

    @pytest.mark.asyncio
    async def test_fallback_to_chatter_name_when_no_display_name(
        self, component: GamesComponent
    ) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx(display_name="", name="rawname")
            await _roll(component, ctx)
            text: str = ctx.reply.call_args[0][0]
            assert "rawname" in text


# ---------------------------------------------------------------------------
# !choose
# ---------------------------------------------------------------------------


class TestChoose:
    @pytest.mark.asyncio
    async def test_disabled_command_no_reply(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=None):
            ctx = _make_ctx()
            await _choose(component, ctx, args="a b")
            ctx.reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_args_returns_usage(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            await _choose(component, ctx)
            text: str = ctx.reply.call_args[0][0]
            assert "用法" in text

    @pytest.mark.asyncio
    async def test_empty_args_returns_usage(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            await _choose(component, ctx, args="   ")
            text: str = ctx.reply.call_args[0][0]
            assert "用法" in text

    @pytest.mark.asyncio
    async def test_single_option_returns_error(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            await _choose(component, ctx, args="only")
            text: str = ctx.reply.call_args[0][0]
            assert "兩個" in text

    @pytest.mark.asyncio
    async def test_two_options_picks_one(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            await _choose(component, ctx, args="red blue")
            text: str = ctx.reply.call_args[0][0]
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
                text: str = ctx.reply.call_args[0][0]
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
            text: str = ctx.reply.call_args[0][0]
            assert str(_MAX_OPTIONS) in text

    @pytest.mark.asyncio
    async def test_exactly_max_options_accepted(self, component: GamesComponent) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx()
            exact = " ".join(f"opt{i}" for i in range(_MAX_OPTIONS))
            await _choose(component, ctx, args=exact)
            text: str = ctx.reply.call_args[0][0]
            assert "🎯" in text

    @pytest.mark.asyncio
    async def test_fallback_to_chatter_name_when_no_display_name(
        self, component: GamesComponent
    ) -> None:
        with patch(PATCH_CHECK, return_value=MagicMock()):
            ctx = _make_ctx(display_name="", name="rawname")
            await _choose(component, ctx, args="x y")
            text: str = ctx.reply.call_args[0][0]
            assert "rawname" in text
