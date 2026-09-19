"""Channel management API routes"""

import asyncio
import logging

from asyncpg import Pool
from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.config import Settings, get_settings
from core.dependencies import (
    get_channel_service,
    get_current_channel_id,
    get_db_pool,
    get_twitch_api,
    require_activated,
    require_self_tenant_access,
)
from services import ChannelService, TenantContext, TwitchAPIClient
from services.emote_sync import (
    EmoteItem,
    OtherChannelEmotes,
    available_emote_names,
    build_other_channel_groups,
    fetch_channel_emotes,
    resolve_bot_id,
    sync_enabled_emotes_background,
    to_emote_items,
)
from shared.errors import AccessDeniedError, AppError, ChannelNotFoundError, UpstreamError
from shared.repositories.channel import ChannelRepository

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channels", tags=["channels"])


class ChannelAccessDeniedError(AccessDeniedError):
    code = "CHANNEL.ACCESS_DENIED"
    user_message = "你沒有權限操作這個頻道"


class ChannelToggleFailedError(AppError):
    code = "CHANNEL.TOGGLE_FAILED"
    http_status = 500
    user_message = "頻道開關切換失敗，請稍後再試"


class BotNotConfiguredError(AppError):
    code = "CHANNEL.BOT_NOT_CONFIGURED"
    http_status = 503
    user_message = "機器人尚未設定完成，請稍後再試"


class TwitchUnavailableError(UpstreamError):
    code = "CHANNEL.TWITCH_UNAVAILABLE"
    user_message = "Twitch 暫時沒有回應，請稍後再試"


class ChannelToggleRequest(BaseModel):
    channel_id: str
    enabled: bool


class ChannelInfo(BaseModel):
    id: str
    name: str
    display_name: str
    avatar: str
    is_live: bool
    viewer_count: int = 0
    game_name: str = ""
    title: str = ""


class ChannelStatusResponse(BaseModel):
    subscribed: bool
    channel_id: str
    channel_name: str


class ToggleResponse(BaseModel):
    message: str


class ChannelDefaultsResponse(BaseModel):
    default_cooldown: int


class ChannelDefaultsUpdate(BaseModel):
    default_cooldown: int | None = None


class ModStatusResponse(BaseModel):
    is_moderator: bool


class ChannelEmotesResponse(BaseModel):
    bot_user_id: str
    bot_token_available: bool
    emotes: list[EmoteItem]
    # Emotes the bot account has unlocked on OTHER channels (e.g. subscription
    # emotes, usable anywhere once unlocked) — not limited to channels Niibot
    # itself monitors.
    other_channels: list[OtherChannelEmotes]


class GrantModResponse(BaseModel):
    granted: bool
    already_mod: bool = False


@router.get("/twitch/monitored", response_model=list[ChannelInfo])
async def get_monitored_channels(
    channel_id: str = Depends(get_current_channel_id),
    channel_service: ChannelService = Depends(get_channel_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> list[ChannelInfo]:
    """Get list of monitored channels with their live status.

    Uses app access token for Twitch API calls (public endpoints).
    User token is not required for fetching user info and stream status.
    """
    enabled_channels = await channel_service.get_enabled_channels()
    LOGGER.debug("Found %d enabled channels", len(enabled_channels))

    if not enabled_channels:
        return []

    channel_ids = [ch["channel_id"] for ch in enabled_channels]

    # Fetch user info and stream status in parallel (both use app token)
    users_data, streams_data = await asyncio.gather(
        twitch_api.get_users_by_ids(channel_ids),
        twitch_api.get_streams(channel_ids),
    )

    if not users_data:
        LOGGER.warning("No user data returned from Twitch API")
        return []

    # Index live streams by user_id for O(1) lookup
    live_map: dict[str, dict] = {s["user_id"]: s for s in streams_data}

    # Build channel info list
    channels_info: dict[str, ChannelInfo] = {}
    for user in users_data:
        uid = user["id"]
        stream = live_map.get(uid)
        channels_info[user["login"]] = ChannelInfo(
            id=uid,
            name=user["login"],
            display_name=user["display_name"],
            avatar=user["profile_image_url"],
            is_live=stream is not None,
            viewer_count=stream["viewer_count"] if stream else 0,
            game_name=stream["game_name"] if stream else "",
            title=stream["title"] if stream else "",
        )

    # Filter out the current user's channel and sort
    result = [ch for ch in channels_info.values() if ch.id != channel_id]
    result.sort(key=lambda x: (not x.is_live, x.display_name))

    LOGGER.debug("Returning %d monitored channels", len(result))
    return result


@router.get("/twitch/my-status", response_model=ChannelStatusResponse)
async def get_my_channel_status(
    channel_id: str = Depends(get_current_channel_id),
    channel_service: ChannelService = Depends(get_channel_service),
) -> ChannelStatusResponse:
    """Get current user's channel status"""
    status = await channel_service.get_channel_status(channel_id)
    return ChannelStatusResponse(**status)


@router.post("/twitch/toggle", response_model=ToggleResponse)
async def toggle_channel(
    request: ChannelToggleRequest,
    ctx: TenantContext = Depends(require_self_tenant_access),
    channel_service: ChannelService = Depends(get_channel_service),
) -> ToggleResponse:
    """Enable or disable bot for a channel.

    Exemplar for the new tenant-access dependency. ``require_self_tenant_access``
    verifies the caller actually holds at least 'manager' role on the channel
    via channel_members rather than trusting JWT alone — relevant for the
    future mod-delegation flow. The legacy `get_current_channel_id`
    dependency is still wired into the other endpoints in this file and is
    safe to swap incrementally.
    """
    channel_id = ctx.channel_id
    if request.channel_id != channel_id:
        raise ChannelAccessDeniedError(context={"target_channel_id": request.channel_id})

    success = await channel_service.toggle_channel(channel_id, request.enabled)
    if not success:
        raise ChannelToggleFailedError(context={"enabled": request.enabled})

    action = "enabled" if request.enabled else "disabled"
    LOGGER.info("channel_toggled", extra={"action": action})
    return ToggleResponse(message=f"Channel {action} successfully")


@router.get("/twitch/mod-status", response_model=ModStatusResponse)
async def get_bot_mod_status(
    channel_id: str = Depends(get_current_channel_id),
    channel_service: ChannelService = Depends(get_channel_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    settings: Settings = Depends(get_settings),
) -> ModStatusResponse:
    """Check whether the bot currently holds moderator status in the caller's channel."""
    token = await channel_service.get_token_with_refresh(channel_id, twitch_api)
    if not token:
        return JSONResponse(  # type: ignore[return-value]
            status_code=403,
            headers={"X-Reauth-Required": "true"},
            content={"detail": "Token unavailable or missing required scope"},
        )
    bot_id = settings.bot_id
    if not bot_id:
        raise BotNotConfiguredError()
    is_mod = await twitch_api.check_bot_is_moderator(channel_id, bot_id, token)
    return ModStatusResponse(is_moderator=is_mod)


@router.post("/twitch/grant-mod", response_model=GrantModResponse)
async def grant_bot_mod(
    channel_id: str = Depends(get_current_channel_id),
    channel_service: ChannelService = Depends(get_channel_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    settings: Settings = Depends(get_settings),
) -> GrantModResponse:
    """Grant the bot moderator status in the caller's channel."""
    token = await channel_service.get_token_with_refresh(channel_id, twitch_api)
    if not token:
        return JSONResponse(  # type: ignore[return-value]
            status_code=403,
            headers={"X-Reauth-Required": "true"},
            content={"detail": "Token unavailable or missing required scope"},
        )

    bot_id = settings.bot_id
    if not bot_id:
        raise BotNotConfiguredError()
    resp = await twitch_api.add_moderator(channel_id, bot_id, token)

    if resp.status_code == 204:
        LOGGER.info("bot_mod_granted")
        return GrantModResponse(granted=True)

    if resp.status_code == 422:
        return GrantModResponse(granted=False, already_mod=True)

    if resp.status_code in (401, 403):
        return JSONResponse(  # type: ignore[return-value]
            status_code=403,
            headers={"X-Reauth-Required": "true"},
            content={"detail": "Missing required Twitch scope"},
        )

    raise TwitchUnavailableError(
        context={"helix_status": resp.status_code, "helix_body": resp.text}
    )


@router.get("/defaults", response_model=ChannelDefaultsResponse)
async def get_channel_defaults(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> ChannelDefaultsResponse:
    """Get channel default cooldown settings."""
    repo = ChannelRepository(pool)
    channel = await repo.get_channel(channel_id)
    if not channel:
        return ChannelDefaultsResponse(default_cooldown=0)
    return ChannelDefaultsResponse(
        default_cooldown=channel.default_cooldown,
    )


@router.put("/defaults", response_model=ChannelDefaultsResponse)
async def update_channel_defaults(
    body: ChannelDefaultsUpdate,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> ChannelDefaultsResponse:
    """Update channel default cooldown settings."""
    repo = ChannelRepository(pool)
    channel = await repo.update_channel_defaults(
        channel_id,
        default_cooldown=body.default_cooldown,
    )
    if not channel:
        raise ChannelNotFoundError(context={"channel_id": channel_id})
    LOGGER.info("channel_defaults_updated")
    return ChannelDefaultsResponse(
        default_cooldown=channel.default_cooldown,
    )


@router.get("/emotes", response_model=ChannelEmotesResponse)
async def get_channel_emotes(
    background_tasks: BackgroundTasks,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
    twitch: TwitchAPIClient = Depends(get_twitch_api),
    settings: Settings = Depends(get_settings),
    _: None = Depends(require_activated),
) -> ChannelEmotesResponse:
    """Return all channel + global emotes with the channel's CURRENT bot
    account's availability status, PLUS any emotes that account has unlocked
    on other channels (e.g. subscription emotes, usable anywhere once
    unlocked) — usable anywhere the bot can send a chat message (custom
    commands, events, AI replies), not just AI settings.

    Availability is determined by fetching that account's accessible emotes via
    its user token (requires user:read:emotes scope). Falls back to unavailable
    for subscription/bits emotes if the bot token is missing or the scope is
    not yet granted.
    """
    bot_id = await resolve_bot_id(pool, channel_id, system_bot_id=settings.bot_id)
    token_row = await ChannelRepository(pool).get_token(bot_id, "bot")
    bot_token = token_row.token if token_row else None

    fetch = await fetch_channel_emotes(twitch, channel_id, bot_id=bot_id, bot_token=bot_token)
    items = to_emote_items(fetch)
    other_channels = await build_other_channel_groups(twitch, fetch)

    available_names = available_emote_names(fetch.channel_raw, fetch.global_raw, fetch.accessible)
    background_tasks.add_task(sync_enabled_emotes_background, pool, channel_id, available_names)
    return ChannelEmotesResponse(
        bot_user_id=bot_id,
        bot_token_available=fetch.bot_token_available,
        emotes=items,
        other_channels=other_channels,
    )
