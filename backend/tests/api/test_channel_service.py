"""ChannelService delegates token lifecycle to the locked authorization boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.channel_service import ChannelService
from services.twitch_authorization_service import CredentialHealth
from shared.twitch_scopes import BROADCASTER_CORE_SCOPES


@pytest.mark.asyncio
async def test_get_token_with_refresh_uses_locked_core_health_check() -> None:
    pool = MagicMock()
    twitch = MagicMock(client_id="client-1")
    service = ChannelService(pool)
    service.repo.get_token = AsyncMock(return_value=SimpleNamespace(token="fresh-access"))

    with patch("services.channel_service.TwitchAuthorizationService") as authorization_cls:
        authorization = authorization_cls.return_value
        authorization.check_credential = AsyncMock(
            return_value=CredentialHealth(
                user_id="channel-1",
                token_type="broadcaster",
                status="valid",
            )
        )

        token = await service.get_token_with_refresh("channel-1", twitch)

    assert token == "fresh-access"
    authorization.check_credential.assert_awaited_once_with(
        user_id="channel-1",
        token_type="broadcaster",
        required_scopes=set(BROADCASTER_CORE_SCOPES),
    )


@pytest.mark.asyncio
async def test_get_token_with_refresh_does_not_return_invalid_credential() -> None:
    service = ChannelService(MagicMock())
    service.repo.get_token = AsyncMock()

    with patch("services.channel_service.TwitchAuthorizationService") as authorization_cls:
        authorization = authorization_cls.return_value
        authorization.check_credential = AsyncMock(
            return_value=CredentialHealth(
                user_id="channel-1",
                token_type="broadcaster",
                status="requires_reauthorization",
            )
        )

        token = await service.get_token_with_refresh("channel-1", MagicMock(client_id="client-1"))

    assert token is None
    service.repo.get_token.assert_not_awaited()
