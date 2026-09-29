"""Focused tests for command catalog metadata and public visibility."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.command_config_service import CommandConfigService, CommandNameConflictError
from shared.models.command_config import CommandConfig

pytestmark = pytest.mark.asyncio


def _command(
    name: str,
    *,
    command_type: str = "builtin",
    min_role: str = "everyone",
    response: str | None = None,
    aliases: str | None = None,
) -> CommandConfig:
    return CommandConfig(
        id=None,
        channel_id="channel-1",
        command_name=name,
        command_type=command_type,
        enabled=True,
        min_role=min_role,
        custom_response=response,
        aliases=aliases,
    )


async def test_public_commands_only_expose_viewer_facing_roles() -> None:
    service = object.__new__(CommandConfigService)
    service.pool = MagicMock()
    service.cmd_repo = MagicMock()
    service.cmd_repo.list_configs = AsyncMock(
        return_value=[
            _command("help"),
            _command("subcount", min_role="broadcaster"),
            _command("condemn", min_role="moderator"),
            _command("hello", command_type="custom", response="Hello chat"),
            _command("cmd", command_type="custom", response="Legacy shadow"),
            _command(
                "mod-note",
                command_type="custom",
                min_role="moderator",
                response="Mod only",
            ),
        ]
    )
    trigger_repo = MagicMock()
    trigger_repo.list_enabled = AsyncMock(
        return_value=[
            SimpleNamespace(pattern="gg", response="GG!", min_role="subscriber"),
            SimpleNamespace(pattern="mod", response="Mod!", min_role="moderator"),
        ]
    )

    with patch(
        "services.command_config_service.MessageTriggerRepository",
        return_value=trigger_repo,
    ):
        result = await service.list_public_commands("channel-1")

    assert [item["name"] for item in result] == ["!help", "!hello", "gg"]
    assert [item["min_role"] for item in result] == ["everyone", "everyone", "subscriber"]


async def test_dashboard_commands_include_explanatory_metadata() -> None:
    service = object.__new__(CommandConfigService)
    service.cmd_repo = MagicMock()
    service.cmd_repo.list_configs = AsyncMock(return_value=[_command("subage")])

    [result] = await service.list_commands("channel-1")

    assert result["audience"] == "viewer"
    assert result["usage"] == "!subage"
    assert "累積訂閱月數" in result["detail"]
    assert result["preview_input"] == "!subage"
    assert "14 個月" in result["preview_output"]
    assert result["public_visible"] is True


async def test_dashboard_commands_include_external_capability_contract() -> None:
    service = object.__new__(CommandConfigService)
    service.cmd_repo = MagicMock()
    service.cmd_repo.list_configs = AsyncMock(
        return_value=[_command("marker", min_role="moderator")]
    )

    [result] = await service.list_commands("channel-1")

    assert result["integration_kind"] == "twitch_capability"
    assert result["integration_label"] == "Twitch 直播標記"
    assert result["capability_requirements"] == [
        {
            "capability_key": "channel_info",
            "mode": "all",
            "requires_bot_moderator": False,
        }
    ]
    assert "直播中" in " ".join(result["external_conditions"])


async def test_create_custom_command_rejects_runtime_reserved_name() -> None:
    service = object.__new__(CommandConfigService)
    service.cmd_repo = MagicMock()
    service.cmd_repo.list_configs = AsyncMock(return_value=[])

    with pytest.raises(CommandNameConflictError):
        await service.create_custom_command(
            "channel-1",
            "gq",
            custom_response="shadow game queue",
        )

    service.cmd_repo.try_insert_config.assert_not_called()


async def test_create_custom_command_rejects_reserved_alias() -> None:
    service = object.__new__(CommandConfigService)
    service.cmd_repo = MagicMock()
    service.cmd_repo.list_configs = AsyncMock(return_value=[])

    with pytest.raises(CommandNameConflictError):
        await service.create_custom_command(
            "channel-1",
            "hello",
            custom_response="Hello!",
            aliases="xhc",
        )

    service.cmd_repo.try_insert_config.assert_not_called()


@pytest.mark.parametrize("alias", ["標題", "抽", "選", "刪"])
async def test_create_custom_command_rejects_concise_builtin_alias(alias: str) -> None:
    service = object.__new__(CommandConfigService)
    service.cmd_repo = MagicMock()
    service.cmd_repo.list_configs = AsyncMock(return_value=[])

    with pytest.raises(CommandNameConflictError):
        await service.create_custom_command(
            "channel-1",
            "hello",
            custom_response="Hello!",
            aliases=alias,
        )

    service.cmd_repo.try_insert_config.assert_not_called()


async def test_create_custom_command_uses_insert_only_repository_primitive() -> None:
    created = _command("hello", command_type="custom", response="Hello!")
    service = object.__new__(CommandConfigService)
    service.cmd_repo = MagicMock()
    service.cmd_repo.list_configs = AsyncMock(return_value=[])
    service.cmd_repo.try_insert_config = AsyncMock(return_value=created)

    result = await service.create_custom_command(
        "channel-1",
        "hello",
        custom_response="Hello!",
    )

    assert result["command_name"] == "hello"
    service.cmd_repo.try_insert_config.assert_awaited_once()
    service.cmd_repo.upsert_config.assert_not_called()


async def test_create_custom_command_rejects_concurrent_duplicate() -> None:
    service = object.__new__(CommandConfigService)
    service.cmd_repo = MagicMock()
    service.cmd_repo.list_configs = AsyncMock(return_value=[])
    service.cmd_repo.try_insert_config = AsyncMock(return_value=None)

    with pytest.raises(CommandNameConflictError):
        await service.create_custom_command(
            "channel-1",
            "hello",
            custom_response="Hello!",
        )


async def test_update_custom_command_rejects_runtime_reserved_alias() -> None:
    current = _command("hello", command_type="custom", response="Hello!")
    service = object.__new__(CommandConfigService)
    service.cmd_repo = MagicMock()
    service.cmd_repo.get_config = AsyncMock(return_value=current)
    service.cmd_repo.list_configs = AsyncMock(return_value=[current])

    with pytest.raises(CommandNameConflictError):
        await service.update_command("channel-1", "hello", aliases="xhc")

    service.cmd_repo.upsert_config.assert_not_called()


async def test_legacy_reserved_custom_command_cannot_be_reenabled() -> None:
    current = _command("cmd", command_type="custom", response="Legacy shadow")
    current.enabled = False
    service = object.__new__(CommandConfigService)
    service.cmd_repo = MagicMock()
    service.cmd_repo.get_config = AsyncMock(return_value=current)

    with pytest.raises(CommandNameConflictError):
        await service.toggle_command("channel-1", "cmd", True)

    service.cmd_repo.upsert_config.assert_not_called()


async def test_update_builtin_allows_its_own_catalog_alias() -> None:
    current = _command("crosshairs", aliases="xhc,準星")
    service = object.__new__(CommandConfigService)
    service.cmd_repo = MagicMock()
    service.cmd_repo.get_config = AsyncMock(return_value=current)
    service.cmd_repo.list_configs = AsyncMock(return_value=[current])
    service.cmd_repo.upsert_config = AsyncMock(return_value=current)

    result = await service.update_command(
        "channel-1",
        "crosshairs",
        aliases="xhc,準星",
    )

    assert result["command_name"] == "crosshairs"
    service.cmd_repo.upsert_config.assert_awaited_once()
