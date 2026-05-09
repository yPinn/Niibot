"""Crosshair repository API routes"""

import logging
from datetime import datetime
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.dependencies import get_current_channel_id, get_db_pool, get_twitch_api
from services import TwitchAPIClient
from shared.cache import AsyncTTLCache
from shared.repositories.crosshair import VALID_GAMES, CrosshairRepository

LOGGER: logging.Logger = logging.getLogger(__name__)

_user_lookup_cache: AsyncTTLCache = AsyncTTLCache(maxsize=256, ttl=60.0)

router = APIRouter(prefix="/api/crosshairs", tags=["crosshairs"])


class CrosshairResponse(BaseModel):
    id: UUID
    channel_id: str
    game: str
    name: str
    code: str
    description: str | None = None
    display_order: int
    created_at: datetime
    updated_at: datetime


class PublicChannelProfile(BaseModel):
    display_name: str | None = None
    profile_image_url: str | None = None


class PublicCrosshairsResponse(BaseModel):
    channel: PublicChannelProfile
    crosshairs: list[CrosshairResponse]


class CrosshairCreate(BaseModel):
    game: str
    name: str = Field(max_length=100)
    code: str = Field(max_length=2000)
    description: str | None = Field(None, max_length=500)
    display_order: int = 0


class CrosshairUpdate(BaseModel):
    game: str | None = None
    name: str | None = Field(None, max_length=100)
    code: str | None = Field(None, max_length=2000)
    description: str | None = Field(None, max_length=500)
    display_order: int | None = None


class CrosshairWithChannelResponse(CrosshairResponse):
    channel_name: str


@router.get("/public", response_model=list[CrosshairWithChannelResponse])
async def list_all_public_crosshairs(
    game: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[CrosshairWithChannelResponse]:
    """List recent crosshairs from all channels (public, no auth)."""
    try:
        repo = CrosshairRepository(pool)
        rows = await repo.list_all_public(game=game, limit=limit)
        return [CrosshairWithChannelResponse(**row) for row in rows]
    except Exception:
        LOGGER.exception("Failed to list all public crosshairs")
        raise HTTPException(status_code=500, detail="Failed to fetch crosshairs") from None


@router.get("/public/{username}", response_model=PublicCrosshairsResponse)
async def get_public_crosshairs(
    username: str,
    game: str | None = Query(None),
    pool: asyncpg.Pool = Depends(get_db_pool),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> PublicCrosshairsResponse:
    """List crosshairs for a channel (public, no auth)."""
    cache_key = f"user_by_login:{username.lower()}"
    if cache_key in _user_lookup_cache:
        user_info = _user_lookup_cache.get(cache_key)
    else:
        user_info = await twitch_api.get_user_by_login(username)
        if user_info:
            _user_lookup_cache.set(cache_key, user_info)

    if not user_info:
        raise HTTPException(status_code=404, detail="Channel not found")

    try:
        repo = CrosshairRepository(pool)
        rows = await repo.list_by_channel(user_info["id"], game=game)
        return PublicCrosshairsResponse(
            channel=PublicChannelProfile(
                display_name=user_info.get("display_name"),
                profile_image_url=user_info.get("avatar"),
            ),
            crosshairs=[CrosshairResponse(**row) for row in rows],
        )
    except Exception:
        LOGGER.exception("Failed to get public crosshairs")
        raise HTTPException(status_code=500, detail="Failed to fetch crosshairs") from None


@router.get("", response_model=list[CrosshairResponse])
async def list_crosshairs(
    game: str | None = Query(None),
    channel_id: str = Depends(get_current_channel_id),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> list[CrosshairResponse]:
    """List crosshairs for the authenticated channel."""
    try:
        repo = CrosshairRepository(pool)
        rows = await repo.list_by_channel(channel_id, game=game)
        return [CrosshairResponse(**row) for row in rows]
    except Exception:
        LOGGER.exception("Failed to list crosshairs")
        raise HTTPException(status_code=500, detail="Failed to fetch crosshairs") from None


@router.post("", response_model=CrosshairResponse, status_code=201)
async def create_crosshair(
    body: CrosshairCreate,
    channel_id: str = Depends(get_current_channel_id),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> CrosshairResponse:
    """Create a crosshair entry."""
    if body.game not in VALID_GAMES:
        raise HTTPException(status_code=400, detail=f"Invalid game: {body.game}")
    try:
        repo = CrosshairRepository(pool)
        row = await repo.create(
            channel_id,
            game=body.game,
            name=body.name,
            code=body.code,
            description=body.description,
            display_order=body.display_order,
        )
        return CrosshairResponse(**row)
    except Exception:
        LOGGER.exception("Failed to create crosshair")
        raise HTTPException(status_code=500, detail="Failed to create crosshair") from None


@router.patch("/{crosshair_id}", response_model=CrosshairResponse)
async def update_crosshair(
    crosshair_id: UUID,
    body: CrosshairUpdate,
    channel_id: str = Depends(get_current_channel_id),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> CrosshairResponse:
    """Update a crosshair entry."""
    if body.game is not None and body.game not in VALID_GAMES:
        raise HTTPException(status_code=400, detail=f"Invalid game: {body.game}")
    fields = body.model_dump(exclude_unset=True)
    try:
        repo = CrosshairRepository(pool)
        row = await repo.update(str(crosshair_id), channel_id, fields=fields)
        if row is None:
            raise HTTPException(status_code=404, detail="Crosshair not found")
        return CrosshairResponse(**row)
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to update crosshair")
        raise HTTPException(status_code=500, detail="Failed to update crosshair") from None


@router.delete("/{crosshair_id}", status_code=204)
async def delete_crosshair(
    crosshair_id: UUID,
    channel_id: str = Depends(get_current_channel_id),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> None:
    """Delete a crosshair entry."""
    try:
        repo = CrosshairRepository(pool)
        deleted = await repo.delete(str(crosshair_id), channel_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Crosshair not found")
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to delete crosshair")
        raise HTTPException(status_code=500, detail="Failed to delete crosshair") from None
