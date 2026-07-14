"""Unit tests for twitch.components.command_manager — CommandManagerComponent.

Covers the !cmd a TOCTOU fix: adding a new command/trigger must be atomic
(insert-or-reject via the DB unique constraint) instead of a separate
existence check followed by an upsert that can never fail.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from twitch.components.command_manager import CommandManagerComponent


def _make_bot() -> MagicMock:
    bot = MagicMock()
    bot.token_database = MagicMock()
    bot.message_trigger_configs = MagicMock()
    return bot


def _make_ctx(*, channel_id: str = "ch_test", moderator: bool = True) -> MagicMock:
    ctx = MagicMock()
    ctx.chatter.moderator = moderator
    ctx.chatter.name = "mod_user"
    ctx.channel.id = channel_id
    ctx.channel.name = "streamer"
    return ctx


@pytest.fixture()
def component() -> CommandManagerComponent:
    comp = CommandManagerComponent(_make_bot())
    comp._ctx_reply = AsyncMock()
    comp.cmd_repo = MagicMock()
    return comp


async def _cmd_add(component: CommandManagerComponent, ctx: MagicMock, args: str) -> None:
    await CommandManagerComponent.cmd_add.callback(component, ctx, args=args)  # type: ignore[attr-defined]


class TestCommandAddAtomicity:
    @pytest.mark.asyncio
    async def test_new_command_is_created_via_atomic_insert(
        self, component: CommandManagerComponent
    ) -> None:
        component.cmd_repo.try_insert_config = AsyncMock(return_value=MagicMock(aliases=None))

        await _cmd_add(component, _make_ctx(), "!newcmd hello there")

        component.cmd_repo.try_insert_config.assert_awaited_once()
        reply_text = component._ctx_reply.call_args[0][1]
        assert "已新增" in reply_text

    @pytest.mark.asyncio
    async def test_conflicting_insert_reports_already_exists_without_overwriting(
        self, component: CommandManagerComponent
    ) -> None:
        """The core of the fix: a conflict must be reported, never silently applied."""
        component.cmd_repo.try_insert_config = AsyncMock(return_value=None)

        await _cmd_add(component, _make_ctx(), "!existing hello there")

        reply_text = component._ctx_reply.call_args[0][1]
        assert "已存在" in reply_text

    @pytest.mark.asyncio
    async def test_builtin_name_rejected_without_hitting_the_database(
        self, component: CommandManagerComponent
    ) -> None:
        component.cmd_repo.try_insert_config = AsyncMock()

        await _cmd_add(component, _make_ctx(), "!ping hello there")

        component.cmd_repo.try_insert_config.assert_not_called()
        reply_text = component._ctx_reply.call_args[0][1]
        assert "已存在" in reply_text

    @pytest.mark.asyncio
    async def test_non_moderator_cannot_add(self, component: CommandManagerComponent) -> None:
        component.cmd_repo.try_insert_config = AsyncMock()

        await _cmd_add(component, _make_ctx(moderator=False), "!newcmd hello")

        component.cmd_repo.try_insert_config.assert_not_called()
        component._ctx_reply.assert_not_called()


class TestTriggerAddAtomicity:
    @pytest.mark.asyncio
    async def test_new_trigger_is_created_via_atomic_insert(
        self, component: CommandManagerComponent
    ) -> None:
        component.bot.message_trigger_configs.try_insert = AsyncMock(return_value=MagicMock())

        await _cmd_add(component, _make_ctx(), "hello there")

        component.bot.message_trigger_configs.try_insert.assert_awaited_once()
        reply_text = component._ctx_reply.call_args[0][1]
        assert "已新增" in reply_text

    @pytest.mark.asyncio
    async def test_conflicting_trigger_with_same_pattern_reports_already_exists(
        self, component: CommandManagerComponent
    ) -> None:
        component.bot.message_trigger_configs.try_insert = AsyncMock(return_value=None)
        component.bot.message_trigger_configs.get_by_name = AsyncMock(
            return_value=MagicMock(pattern="hello")
        )

        await _cmd_add(component, _make_ctx(), "hello there")

        reply_text = component._ctx_reply.call_args[0][1]
        assert "已存在" in reply_text

    @pytest.mark.asyncio
    async def test_conflicting_trigger_with_different_pattern_reports_name_collision(
        self, component: CommandManagerComponent
    ) -> None:
        component.bot.message_trigger_configs.try_insert = AsyncMock(return_value=None)
        component.bot.message_trigger_configs.get_by_name = AsyncMock(
            return_value=MagicMock(pattern="hello world")
        )

        await _cmd_add(component, _make_ctx(), "hello there")

        reply_text = component._ctx_reply.call_args[0][1]
        assert "衝突" in reply_text
