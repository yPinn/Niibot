"""Bot sender selection policy and desired-state write contracts."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, call

import pytest
from api.services.bot_selection_service import (
    BotSelectionAccountUnavailableError,
    BotSelectionAuthorizationRequiredError,
    BotSelectionModeratorRequiredError,
    BotSelectionProviderUnavailableError,
    BotSelectionSameIdentityUnsupportedError,
    BotSelectionScopeRequiredError,
    BotSelectionService,
)

from shared.models.channel import Token
from shared.repositories.bot_selection import BotSelectionState
from shared.twitch_scopes import BOT_SCOPES, required_core_scopes


def _state(**overrides) -> BotSelectionState:
    values = {
        "channel_id": "channel-a",
        "desired_bot_user_id": "bot-b",
        "active_bot_user_id": None,
        "selection_version": 1,
        "acked_version": 0,
        "status": "switching",
        "last_error_code": None,
    }
    values.update(overrides)
    return BotSelectionState(**values)


def _health(status: str = "valid") -> MagicMock:
    return MagicMock(status=status, error_code=None)


def _service() -> tuple[BotSelectionService, AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
    repository = AsyncMock()
    authorization = AsyncMock()
    twitch = AsyncMock()
    tokens = AsyncMock()
    tokens.invalidate_token = MagicMock()
    tokens.get_token_scopes.return_value = (False, None)
    repository.is_candidate_available.return_value = True
    repository.request.return_value = _state()
    authorization.check_credential.side_effect = [_health(), _health()]

    async def get_token(user_id: str, token_type: str):
        if token_type == "bot":
            return Token(
                user_id=user_id,
                token="bot-access",
                refresh="bot-refresh",
                token_type="bot",
                scopes=" ".join(BOT_SCOPES),
            )
        return Token(
            user_id="channel-a",
            token="broadcaster-access",
            refresh="broadcaster-refresh",
            token_type="broadcaster",
        )

    tokens.get_token.side_effect = get_token
    twitch.get_bot_mod_status.return_value = "mod"
    service = BotSelectionService(
        pool=MagicMock(),
        repository=repository,
        authorization=authorization,
        twitch_api=twitch,
        tokens=tokens,
        token_encryption_key="test-key",
        system_bot_id="system-bot",
    )
    return service, repository, authorization, twitch, tokens


@pytest.mark.asyncio
async def test_custom_selection_validates_full_bot_grant_and_mod_relation_before_write():
    service, repository, authorization, twitch, _tokens = _service()

    result = await service.request_selection(
        channel_id="channel-a",
        bot_user_id="bot-b",
        actor_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )

    assert result == _state()
    assert authorization.check_credential.await_args_list == [
        call(
            user_id="bot-b",
            token_type="bot",
            required_scopes=set(required_core_scopes("bot")),
        ),
        call(
            user_id="channel-a",
            token_type="broadcaster",
            required_scopes=set(required_core_scopes("broadcaster")),
        ),
    ]
    twitch.get_bot_mod_status.assert_awaited_once_with("channel-a", "bot-b", "broadcaster-access")
    repository.request.assert_awaited_once_with(
        channel_id="channel-a",
        bot_user_id="bot-b",
        actor_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        system_bot_id="system-bot",
        required_scopes=set(BOT_SCOPES),
    )


@pytest.mark.asyncio
async def test_system_selection_uses_system_identity_but_persists_null_desired():
    service, repository, authorization, twitch, _tokens = _service()
    repository.request.return_value = _state(
        desired_bot_user_id=None,
        active_bot_user_id="bot-b",
    )

    await service.request_selection(
        channel_id="channel-a",
        bot_user_id=None,
        actor_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
    )

    assert authorization.check_credential.await_args_list[0] == call(
        user_id="system-bot",
        token_type="bot",
        required_scopes=set(required_core_scopes("bot")),
    )
    twitch.get_bot_mod_status.assert_awaited_once_with(
        "channel-a", "system-bot", "broadcaster-access"
    )
    assert repository.request.await_args.kwargs["bot_user_id"] is None


@pytest.mark.asyncio
async def test_wrong_tenant_account_is_rejected_before_token_or_provider_work():
    service, repository, authorization, twitch, tokens = _service()
    repository.is_candidate_available.return_value = False

    with pytest.raises(BotSelectionAccountUnavailableError):
        await service.request_selection(
            channel_id="channel-a",
            bot_user_id="bot-from-channel-c",
            actor_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        )

    authorization.check_credential.assert_not_awaited()
    twitch.get_bot_mod_status.assert_not_awaited()
    tokens.get_token.assert_not_awaited()
    repository.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_same_identity_is_rejected_before_candidate_or_provider_work():
    service, repository, authorization, twitch, tokens = _service()

    with pytest.raises(BotSelectionSameIdentityUnsupportedError):
        await service.request_selection(
            channel_id="channel-a",
            bot_user_id="channel-a",
            actor_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        )

    repository.is_candidate_available.assert_not_awaited()
    authorization.check_credential.assert_not_awaited()
    twitch.get_bot_mod_status.assert_not_awaited()
    tokens.get_token.assert_not_awaited()
    repository.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_bot_candidate_already_used_as_broadcaster_is_rejected_before_provider_work():
    service, repository, authorization, twitch, tokens = _service()
    tokens.get_token_scopes.return_value = (True, "channel:bot")

    with pytest.raises(BotSelectionSameIdentityUnsupportedError):
        await service.request_selection(
            channel_id="channel-a",
            bot_user_id="bot-b",
            actor_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        )

    tokens.get_token_scopes.assert_awaited_once_with("bot-b", "broadcaster")
    authorization.check_credential.assert_not_awaited()
    twitch.get_bot_mod_status.assert_not_awaited()
    repository.request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        ("requires_reauthorization", BotSelectionAuthorizationRequiredError),
        ("temporarily_unavailable", BotSelectionProviderUnavailableError),
    ],
)
async def test_unhealthy_bot_credential_never_writes_desired_state(status, error_type):
    service, repository, authorization, _twitch, _tokens = _service()
    authorization.check_credential.side_effect = [_health(status)]

    with pytest.raises(error_type):
        await service.request_selection(
            channel_id="channel-a",
            bot_user_id="bot-b",
            actor_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        )

    repository.request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mod_status", "error_type"),
    [
        ("no_mod", BotSelectionModeratorRequiredError),
        ("scope_error", BotSelectionScopeRequiredError),
        ("token_error", BotSelectionAuthorizationRequiredError),
        ("provider_unavailable", BotSelectionProviderUnavailableError),
    ],
)
async def test_mod_preflight_maps_provider_result_to_safe_domain_error(mod_status, error_type):
    service, repository, _authorization, twitch, _tokens = _service()
    twitch.get_bot_mod_status.return_value = mod_status

    with pytest.raises(error_type):
        await service.request_selection(
            channel_id="channel-a",
            bot_user_id="bot-b",
            actor_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        )

    repository.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_candidate_mapping_is_checked_again_inside_desired_write_transaction():
    service, repository, _authorization, _twitch, _tokens = _service()
    repository.request.return_value = None

    with pytest.raises(BotSelectionAccountUnavailableError):
        await service.request_selection(
            channel_id="channel-a",
            bot_user_id="bot-b",
            actor_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        )


@pytest.mark.asyncio
async def test_missing_broadcaster_credential_is_actionable_and_does_not_write():
    service, repository, _authorization, _twitch, tokens = _service()
    tokens.get_token.side_effect = [
        Token(
            user_id="bot-b",
            token="bot-access",
            refresh="bot-refresh",
            token_type="bot",
            scopes=" ".join(BOT_SCOPES),
        ),
        None,
    ]

    with pytest.raises(BotSelectionAuthorizationRequiredError):
        await service.request_selection(
            channel_id="channel-a",
            bot_user_id="bot-b",
            actor_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        )

    repository.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_optional_bot_scope_gap_blocks_selection_without_invalidating_core_credential():
    service, repository, authorization, _twitch, tokens = _service()
    tokens.get_token.side_effect = [
        Token(
            user_id="bot-b",
            token="bot-access",
            refresh="bot-refresh",
            token_type="bot",
            scopes="user:read:chat user:write:chat user:bot",
        )
    ]

    with pytest.raises(BotSelectionScopeRequiredError):
        await service.request_selection(
            channel_id="channel-a",
            bot_user_id="bot-b",
            actor_user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        )

    authorization.check_credential.assert_awaited_once_with(
        user_id="bot-b",
        token_type="bot",
        required_scopes=set(required_core_scopes("bot")),
    )
    repository.request.assert_not_awaited()
