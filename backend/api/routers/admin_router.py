"""Admin-only API routes — accessible only to the bot owner."""

import asyncio
import logging
from datetime import datetime

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.config import get_settings
from core.dependencies import (
    get_channel_service,
    get_current_channel_id,
    get_db_pool,
    get_twitch_api,
)
from services import ChannelService, TwitchAPIClient
from shared.repositories.activation_request import ActivationRequestRepository

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


async def require_owner(channel_id: str = Depends(get_current_channel_id)) -> str:
    if channel_id != str(get_settings().owner_id):
        raise HTTPException(status_code=403, detail="Owner access required")
    return channel_id


class AdminChannelInfo(BaseModel):
    id: str
    name: str
    display_name: str
    avatar: str
    is_live: bool
    mod_status: str  # 'mod' | 'no_mod' | 'token_error' | 'scope_error'


@router.get("/channels", response_model=list[AdminChannelInfo])
async def get_admin_channels(
    owner_id: str = Depends(require_owner),
    channel_service: ChannelService = Depends(get_channel_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> list[AdminChannelInfo]:
    """Return all monitored channels with mod status. Owner-only."""
    enabled = await channel_service.get_enabled_channels()
    other = [ch for ch in enabled if ch["channel_id"] != owner_id]
    if not other:
        return []

    channel_ids = [ch["channel_id"] for ch in other]
    bot_id = get_settings().bot_id or ""

    users_data, streams_data = await asyncio.gather(
        twitch_api.get_users_by_ids(channel_ids),
        twitch_api.get_streams(channel_ids),
    )
    live_ids = {s["user_id"] for s in streams_data}
    user_map = {u["id"]: u for u in users_data}

    async def _check_mod(channel_id: str) -> tuple[str, str]:
        if not bot_id:
            return channel_id, "token_error"
        token = await channel_service.get_token_with_refresh(channel_id, twitch_api)
        if not token:
            return channel_id, "token_error"
        status = await twitch_api.get_bot_mod_status(channel_id, bot_id, token)
        return channel_id, status

    mod_results = await asyncio.gather(
        *[_check_mod(cid) for cid in channel_ids], return_exceptions=True
    )
    mod_map: dict[str, str] = {}
    for r in mod_results:
        if not isinstance(r, Exception):
            cid, status = r  # type: ignore[misc]
            mod_map[cid] = status

    result = [
        AdminChannelInfo(
            id=cid,
            name=user_map.get(cid, {}).get("login", ""),
            display_name=user_map.get(cid, {}).get("display_name", ""),
            avatar=user_map.get(cid, {}).get("profile_image_url", ""),
            is_live=cid in live_ids,
            mod_status=mod_map.get(cid, "error"),
        )
        for ch in other
        if (cid := ch["channel_id"]) and cid in user_map
    ]

    result.sort(key=lambda x: (x.mod_status != "mod", x.name))
    return result


class PendingCodeInfo(BaseModel):
    platform_user_id: str
    display_name: str | None
    username: str | None
    avatar: str | None
    expires_at: datetime


class ActivationRequestInfo(BaseModel):
    id: int
    platform_user_id: str
    display_name: str | None
    username: str | None
    avatar: str | None
    note: str
    created_at: datetime


@router.get("/activation-codes", response_model=list[PendingCodeInfo])
async def get_pending_activation_codes(
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> list[PendingCodeInfo]:
    """List unused, non-expired OTP activation codes. Owner-only."""
    rows = await pool.fetch(
        """
        SELECT ac.platform_user_id, ac.expires_at,
               u.display_name, u.avatar, ula.username
        FROM activation_codes ac
        LEFT JOIN user_linked_accounts ula
            ON ula.platform = ac.platform AND ula.platform_user_id = ac.platform_user_id
        LEFT JOIN users u ON u.id = ula.user_id
        WHERE ac.used_at IS NULL AND ac.expires_at > NOW()
        ORDER BY ac.expires_at ASC
        """
    )
    return [PendingCodeInfo(**dict(r)) for r in rows]


@router.get("/activation-requests", response_model=list[ActivationRequestInfo])
async def get_activation_requests(
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> list[ActivationRequestInfo]:
    """List pending manual activation requests. Owner-only."""
    repo = ActivationRequestRepository(pool)
    rows = await repo.list_pending()
    return [ActivationRequestInfo(**r) for r in rows]


@router.post("/activation-requests/{request_id}/approve")
async def approve_activation_request(
    request_id: int,
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> dict:
    """Approve a manual activation request, activating the user. Owner-only."""
    repo = ActivationRequestRepository(pool)
    if not await repo.approve(request_id):
        raise HTTPException(status_code=404, detail="Request not found or already reviewed")
    LOGGER.info(f"Activation request {request_id} approved by owner")
    return {"approved": True}


@router.post("/activation-requests/{request_id}/reject")
async def reject_activation_request(
    request_id: int,
    _: str = Depends(require_owner),
    pool: Pool = Depends(get_db_pool),
) -> dict:
    """Reject a manual activation request. Owner-only."""
    repo = ActivationRequestRepository(pool)
    if not await repo.reject(request_id):
        raise HTTPException(status_code=404, detail="Request not found or already reviewed")
    LOGGER.info(f"Activation request {request_id} rejected by owner")
    return {"rejected": True}
