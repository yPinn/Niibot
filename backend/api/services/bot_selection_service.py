"""Policy boundary for requesting a per-channel Twitch bot sender switch."""

from __future__ import annotations

import asyncpg

from services.twitch_api import TwitchAPIClient
from services.twitch_authorization_service import (
    TwitchAuthorizationService,
)
from shared.errors import AccessDeniedError, ConflictError, NotFoundError, ServiceUnavailableError
from shared.repositories.bot_selection import BotSelectionRepository, BotSelectionState
from shared.repositories.channel import ChannelRepository
from shared.twitch_scopes import BOT_SCOPES, required_core_scopes


class BotSelectionAccountUnavailableError(NotFoundError):
    code = "BOT_SELECTION.ACCOUNT_UNAVAILABLE"
    user_message = "這個發言帳號目前無法使用，請重新整理"


class BotSelectionSameIdentityUnsupportedError(ConflictError):
    code = "BOT_SELECTION.SAME_IDENTITY_UNSUPPORTED"
    user_message = "這個帳號不能同時用於頻道和發言，請選擇其他帳號"


class BotSelectionAuthorizationRequiredError(AccessDeniedError):
    code = "BOT_SELECTION.AUTHORIZATION_REQUIRED"
    user_message = "發言帳號授權已失效，請先重新授權"


class BotSelectionScopeRequiredError(AccessDeniedError):
    code = "BOT_SELECTION.SCOPE_REQUIRED"
    user_message = "Twitch 授權不完整，請先重新授權"


class BotSelectionModeratorRequiredError(ConflictError):
    code = "BOT_SELECTION.MODERATOR_REQUIRED"
    user_message = "請先在 Twitch 將這個帳號設為管理員"


class BotSelectionProviderUnavailableError(ServiceUnavailableError):
    code = "BOT_SELECTION.PROVIDER_UNAVAILABLE"
    user_message = "Twitch 暫時無法確認，請稍後再試"


class BotSelectionService:
    def __init__(
        self,
        pool: asyncpg.Pool,
        *,
        authorization: TwitchAuthorizationService,
        twitch_api: TwitchAPIClient,
        token_encryption_key: str,
        system_bot_id: str,
        repository: BotSelectionRepository | None = None,
        tokens: ChannelRepository | None = None,
    ) -> None:
        self.repository = repository or BotSelectionRepository(pool)
        self.authorization = authorization
        self.twitch = twitch_api
        self.tokens = tokens or ChannelRepository(
            pool,
            token_encryption_key=token_encryption_key,
        )
        self.system_bot_id = system_bot_id

    async def get_selection(self, channel_id: str) -> BotSelectionState:
        return await self.repository.get(channel_id)

    @staticmethod
    def _require_healthy(status: str) -> None:
        if status == "temporarily_unavailable":
            raise BotSelectionProviderUnavailableError()
        if status != "valid":
            raise BotSelectionAuthorizationRequiredError()

    async def request_selection(
        self,
        *,
        channel_id: str,
        bot_user_id: str | None,
        actor_user_id: str,
    ) -> BotSelectionState:
        target_id = bot_user_id or self.system_bot_id
        if target_id == channel_id:
            raise BotSelectionSameIdentityUnsupportedError()
        if not target_id or not await self.repository.is_candidate_available(
            channel_id=channel_id,
            bot_user_id=bot_user_id,
            system_bot_id=self.system_bot_id,
        ):
            raise BotSelectionAccountUnavailableError()
        has_broadcaster_credential, _ = await self.tokens.get_token_scopes(
            target_id,
            "broadcaster",
        )
        if has_broadcaster_credential:
            raise BotSelectionSameIdentityUnsupportedError()

        bot_health = await self.authorization.check_credential(
            user_id=target_id,
            token_type="bot",
            required_scopes=set(required_core_scopes("bot")),
        )
        self._require_healthy(bot_health.status)

        # Core credential health and optional feature grants are deliberately
        # separate.  A candidate missing the complete Bot contract cannot be
        # selected, but that gap must not globally invalidate an otherwise
        # valid core chat credential.
        self.tokens.invalidate_token(target_id, "bot")
        bot_token = await self.tokens.get_token(target_id, "bot")
        if bot_token is None:
            raise BotSelectionAuthorizationRequiredError()
        granted_scopes = set((bot_token.scopes or "").split())
        if not set(BOT_SCOPES).issubset(granted_scopes):
            raise BotSelectionScopeRequiredError()

        broadcaster_health = await self.authorization.check_credential(
            user_id=channel_id,
            token_type="broadcaster",
            required_scopes=set(required_core_scopes("broadcaster")),
        )
        self._require_healthy(broadcaster_health.status)
        self.tokens.invalidate_token(channel_id, "broadcaster")
        broadcaster_token = await self.tokens.get_token(channel_id, "broadcaster")
        if broadcaster_token is None:
            raise BotSelectionAuthorizationRequiredError()

        mod_status = await self.twitch.get_bot_mod_status(
            channel_id,
            target_id,
            broadcaster_token.token,
        )
        if mod_status == "no_mod":
            raise BotSelectionModeratorRequiredError()
        if mod_status == "scope_error":
            raise BotSelectionScopeRequiredError()
        if mod_status == "token_error":
            raise BotSelectionAuthorizationRequiredError()
        if mod_status != "mod":
            raise BotSelectionProviderUnavailableError()

        state = await self.repository.request(
            channel_id=channel_id,
            bot_user_id=bot_user_id,
            actor_user_id=actor_user_id,
            system_bot_id=self.system_bot_id,
            required_scopes=set(BOT_SCOPES),
        )
        if state is None:
            raise BotSelectionAccountUnavailableError()
        return state
