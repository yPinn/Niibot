"""Focused tests for command catalog metadata and public visibility."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.command_config_service import CommandConfigService
from shared.models.command_config import CommandConfig

pytestmark = pytest.mark.asyncio


def _command(
    name: str,
    *,
    command_type: str = "builtin",
    min_role: str = "everyone",
    response: str | None = None,
) -> CommandConfig:
    return CommandConfig(
        id=None,
        channel_id="channel-1",
        command_name=name,
        command_type=command_type,
        enabled=True,
        min_role=min_role,
        custom_response=response,
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
