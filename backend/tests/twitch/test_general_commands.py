"""Unit tests for twitch.components.general_commands — the !so shoutout gate.

TwitchIO wraps component methods with a Command descriptor; call
`.callback(component, ctx, ...)` to invoke the raw implementation.

!so used to re-check `ctx.chatter.moderator` itself because virtual builtin
configs were always min_role="everyone". Now the def declares
min_role="moderator" and check_command enforces it, so the handler must rely
on check_command's return alone — no second gate.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from twitch.components.general_commands import GeneralCommandsComponent

PATCH_CHECK = "twitch.components.general_commands.check_command"


def _make_component(
    *, is_mod: bool = True, channel_id: str = "ch_test"
) -> GeneralCommandsComponent:
    bot = MagicMock()
    bot.token_database = MagicMock()
    bot.channels = MagicMock()
    bot._bot_is_mod = {channel_id} if is_mod else set()
    comp = GeneralCommandsComponent(bot)
    comp._ctx_reply = AsyncMock()
    comp._record_command = AsyncMock()
    return comp


def _make_ctx(
    *, moderator: bool = False, broadcaster: bool = False, channel_id: str = "ch_test"
) -> MagicMock:
    ctx = MagicMock()
    ctx.chatter.moderator = moderator
    ctx.chatter.broadcaster = broadcaster
    ctx.chatter.name = "someviewer"
    ctx.chatter.id = "viewer-1"
    ctx.channel.id = channel_id
    ctx.channel.name = "streamer"
    ctx.bot.bot_id = "bot123"
    ctx.bot.sender_for = MagicMock(return_value="bot123")
    ctx.bot.fetch_users = AsyncMock(return_value=[MagicMock(id="target456")])
    ctx.broadcaster.send_shoutout = AsyncMock()
    ctx.broadcaster.timeout_user = AsyncMock()
    return ctx


async def _shoutout(comp: GeneralCommandsComponent, ctx: MagicMock, target: str | None) -> None:
    await GeneralCommandsComponent.shoutout.callback(comp, ctx, target=target)  # type: ignore[attr-defined]


async def _help(comp: GeneralCommandsComponent, ctx: MagicMock) -> None:
    await GeneralCommandsComponent.help.callback(comp, ctx)  # type: ignore[attr-defined]


async def _del(comp: GeneralCommandsComponent, ctx: MagicMock) -> None:
    await GeneralCommandsComponent.delete_own_messages.callback(comp, ctx)  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_help_loads_frontend_url_at_command_time() -> None:
    comp = _make_component()
    ctx = _make_ctx()
    with (
        patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())),
        patch("twitch.components.general_commands.get_settings") as settings,
    ):
        settings.return_value.frontend_url = "https://niibot.tv/"
        await _help(comp, ctx)

    comp._ctx_reply.assert_awaited_once_with(ctx, "指令列表： https://niibot.tv/streamer/commands")


@pytest.mark.asyncio
class TestShoutoutGate:
    async def test_blocked_when_check_command_denies(self):
        """check_command returns None (role / cooldown / disabled) -> no shoutout."""
        comp = _make_component()
        ctx = _make_ctx(moderator=False)
        with patch(PATCH_CHECK, AsyncMock(return_value=None)):
            await _shoutout(comp, ctx, "somechannel")
        ctx.broadcaster.send_shoutout.assert_not_awaited()

    async def test_proceeds_on_check_command_pass_without_a_second_gate(self):
        """When check_command passes, the handler does not re-check moderator itself."""
        comp = _make_component()
        ctx = _make_ctx(moderator=False)  # not a mod, but check_command "passed"
        with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
            await _shoutout(comp, ctx, "somechannel")
        ctx.broadcaster.send_shoutout.assert_awaited_once()

    async def test_usage_hint_when_target_missing(self):
        comp = _make_component()
        ctx = _make_ctx(moderator=True)
        with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
            await _shoutout(comp, ctx, None)
        ctx.broadcaster.send_shoutout.assert_not_awaited()
        comp._ctx_reply.assert_awaited()


@pytest.mark.asyncio
class TestDel:
    async def test_blocked_when_check_command_denies(self):
        comp = _make_component()
        ctx = _make_ctx()
        with patch(PATCH_CHECK, AsyncMock(return_value=None)):
            await _del(comp, ctx)
        ctx.broadcaster.timeout_user.assert_not_awaited()

    async def test_broadcaster_cannot_target_self(self):
        comp = _make_component()
        ctx = _make_ctx(broadcaster=True)
        with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
            await _del(comp, ctx)
        ctx.broadcaster.timeout_user.assert_not_awaited()
        comp._ctx_reply.assert_awaited()

    async def test_silent_when_bot_not_mod(self):
        comp = _make_component(is_mod=False)
        ctx = _make_ctx()
        with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
            await _del(comp, ctx)
        ctx.broadcaster.timeout_user.assert_not_awaited()
        ctx.broadcaster.send_shoutout.assert_not_awaited()

    async def test_times_out_self_for_one_second(self):
        comp = _make_component()
        ctx = _make_ctx()
        with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
            await _del(comp, ctx)
        ctx.broadcaster.timeout_user.assert_awaited_once_with(
            moderator="bot123", user="viewer-1", duration=1, reason="!del 自助清除留言"
        )
        comp._record_command.assert_awaited_once_with(ctx, "del")

    async def test_silent_on_helix_failure(self):
        comp = _make_component()
        ctx = _make_ctx()
        ctx.broadcaster.timeout_user = AsyncMock(side_effect=RuntimeError("boom"))
        with patch(PATCH_CHECK, AsyncMock(return_value=MagicMock())):
            await _del(comp, ctx)
        comp._ctx_reply.assert_not_awaited()
        comp._record_command.assert_not_awaited()
