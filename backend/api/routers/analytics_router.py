"""Analytics API routes"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, field_validator

from core.dependencies import (
    get_analytics_service,
    get_current_channel_id,
    get_db_pool,
    get_twitch_api,
)
from services import AnalyticsService, TwitchAPIClient

LOGGER: logging.Logger = logging.getLogger(__name__)
_background_tasks: set[asyncio.Task] = set()


def _on_background_task_done(task: asyncio.Task) -> None:
    _background_tasks.discard(task)
    if not task.cancelled() and (exc := task.exception()):
        LOGGER.warning("Background profile cache upsert failed: %s", exc)


router = APIRouter(prefix="/api/analytics", tags=["analytics"])


class SessionSummary(BaseModel):
    session_id: int
    channel_id: str
    started_at: datetime
    ended_at: datetime | None
    title: str | None
    game_name: str | None
    game_id: str | None
    duration_hours: float
    total_commands: int
    new_follows: int
    new_subs: int
    raids_received: int


class CommandStat(BaseModel):
    command_name: str
    usage_count: int
    last_used_at: datetime


def _parse_jsonb(v: object) -> object:
    return json.loads(v) if isinstance(v, str) else v


class StreamEvent(BaseModel):
    event_type: str
    user_id: str | None
    username: str | None
    display_name: str | None
    metadata: dict | None
    occurred_at: datetime

    @field_validator("metadata", mode="before")
    @classmethod
    def coerce_metadata(cls, v: object) -> object:
        return _parse_jsonb(v)


class AnalyticsSummary(BaseModel):
    total_sessions: int
    total_stream_hours: float
    total_commands: int
    total_follows: int
    total_subs: int
    avg_session_duration: float
    recent_sessions: list[SessionSummary]


class InsightsChatterStat(BaseModel):
    username: str
    display_name: str | None
    message_count: int


class InsightsCommandStat(BaseModel):
    command_name: str
    usage_count: int


class ChannelInsights(BaseModel):
    total_sessions: int
    total_stream_seconds: int
    total_messages: int
    total_commands: int
    total_follows: int
    total_organic_subs: int
    total_gift_subs: int
    total_raids: int
    total_cheers: int
    total_bits: int
    top_chatters: list[InsightsChatterStat]
    top_commands: list[InsightsCommandStat]


class ViewerSummary(BaseModel):
    user_id: str
    username: str
    display_name: str | None
    total_messages: int
    sessions_attended: int
    last_seen: datetime | None
    watch_seconds: int
    total_bits: int
    total_gifts: int = 0
    engagement_score: float
    is_subscribed: bool = False
    sub_tier: str | None = None
    is_mod: bool = False
    is_vip: bool = False
    follow_since: datetime | None = None


class ViewerEvent(BaseModel):
    event_type: str
    metadata: dict | None
    occurred_at: datetime

    @field_validator("metadata", mode="before")
    @classmethod
    def coerce_metadata(cls, v: object) -> object:
        return _parse_jsonb(v)


class ViewerTwitchStatus(BaseModel):
    is_subscribed: bool
    sub_tier: str | None = None
    sub_gifted: bool | None = None
    sub_gifter: str | None = None
    is_mod: bool = False
    is_vip: bool = False
    is_banned: bool = False
    ban_expires_at: datetime | None = None
    ban_reason: str | None = None


class ViewerSessionAttendance(BaseModel):
    session_id: int
    started_at: datetime
    stream_duration_seconds: int
    viewer_watch_seconds: int
    attended: bool


class ViewerProfile(BaseModel):
    user_id: str
    username: str
    display_name: str | None
    profile_image_url: str | None = None
    offline_image_url: str | None = None
    account_created_at: datetime | None = None
    broadcaster_type: str | None = None
    total_messages: int
    sessions_attended: int
    last_seen: datetime | None
    watch_seconds: int
    total_bits: int
    total_gifts: int = 0
    follow_since: datetime | None = None
    streak_count: int = 0
    best_streak: int = 0
    twitch: ViewerTwitchStatus | None = None
    events: list[ViewerEvent]
    session_attendance: list[ViewerSessionAttendance] = []


class BadgeVersion(BaseModel):
    id: str
    title: str
    image_url_1x: str | None = None
    image_url_2x: str | None = None
    image_url_4x: str | None = None


class ChannelBadgeSets(BaseModel):
    subscriber: list[BadgeVersion] = []
    founder: list[BadgeVersion] = []
    bits: list[BadgeVersion] = []


class ChannelBadgesResponse(BaseModel):
    subscriber_1m: str | None = None
    founder: str | None = None
    sets: ChannelBadgeSets = ChannelBadgeSets()


@router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    response: Response,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    channel_id: str = Depends(get_current_channel_id),
    service: AnalyticsService = Depends(get_analytics_service),
) -> AnalyticsSummary:
    try:
        summary_data = await service.get_summary(channel_id, days)

        response.headers["Cache-Control"] = "private, max-age=300"
        LOGGER.debug(f"Channel {channel_id} requested analytics summary (days={days})")
        return AnalyticsSummary(**summary_data)

    except Exception:
        LOGGER.exception("Failed to get analytics summary")
        raise HTTPException(status_code=500, detail="Failed to fetch analytics") from None


@router.get("/sessions/{session_id}/commands", response_model=list[CommandStat])
async def get_session_commands(
    session_id: int,
    response: Response,
    channel_id: str = Depends(get_current_channel_id),
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[CommandStat]:
    try:
        commands = await service.get_session_commands(session_id, channel_id)

        if commands is None:
            raise HTTPException(status_code=404, detail="Session not found")

        response.headers["Cache-Control"] = "private, max-age=600"
        return [CommandStat(**cmd) for cmd in commands]

    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to get session commands")
        raise HTTPException(status_code=500, detail="Failed to fetch commands") from None


@router.get("/sessions/{session_id}/events", response_model=list[StreamEvent])
async def get_session_events(
    session_id: int,
    response: Response,
    channel_id: str = Depends(get_current_channel_id),
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[StreamEvent]:
    try:
        events = await service.get_session_events(session_id, channel_id)

        if events is None:
            raise HTTPException(status_code=404, detail="Session not found")

        response.headers["Cache-Control"] = "private, max-age=600"
        return [StreamEvent(**event) for event in events]

    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to get session events")
        raise HTTPException(status_code=500, detail="Failed to fetch events") from None


@router.get("/insights", response_model=ChannelInsights)
async def get_insights(
    response: Response,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    channel_id: str = Depends(get_current_channel_id),
    service: AnalyticsService = Depends(get_analytics_service),
) -> ChannelInsights:
    try:
        data = await service.get_insights(channel_id, days)
        response.headers["Cache-Control"] = "private, max-age=300"
        return ChannelInsights(**data)
    except Exception:
        LOGGER.exception("Failed to get channel insights")
        raise HTTPException(status_code=500, detail="Failed to fetch insights") from None


@router.get("/viewers", response_model=list[ViewerSummary])
async def list_viewers(
    response: Response,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    channel_id: str = Depends(get_current_channel_id),
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[ViewerSummary]:
    try:
        viewers = await service.list_viewers(channel_id, days, limit)
        response.headers["Cache-Control"] = "private, max-age=300"
        return [ViewerSummary(**v) for v in viewers]
    except Exception:
        LOGGER.exception("Failed to list viewers")
        raise HTTPException(status_code=500, detail="Failed to fetch viewers") from None


@router.get("/viewers/{user_id}", response_model=ViewerProfile)
async def get_viewer_profile(
    user_id: str,
    response: Response,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    channel_id: str = Depends(get_current_channel_id),
    service: AnalyticsService = Depends(get_analytics_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> ViewerProfile:
    try:
        profile, attendance_rows = await asyncio.gather(
            service.get_viewer_profile(channel_id, user_id, days),
            service.get_viewer_session_attendance(channel_id, user_id, days),
        )
        if profile is None:
            raise HTTPException(status_code=404, detail="Viewer not found")

        status: dict[str, Any] = profile.get("channel_status") or {}
        profile = {k: v for k, v in profile.items() if k != "channel_status"}

        # Profile image cache: use DB value; fetch from Twitch only when missing
        profile_image_url: str | None = status.get("profile_image_url")
        offline_image_url: str | None = status.get("offline_image_url")
        account_created_at: datetime | None = status.get("account_created_at")
        broadcaster_type: str | None = status.get("broadcaster_type")

        if profile_image_url is None:
            try:
                user_info = await twitch_api.get_user_info(user_id)
                if user_info:
                    profile_image_url = user_info.get("avatar") or None
                    offline_image_url = user_info.get("offline_image_url") or None
                    broadcaster_type = user_info.get("broadcaster_type") or None
                    raw_created = user_info.get("account_created_at", "")
                    if raw_created:
                        try:
                            account_created_at = datetime.fromisoformat(
                                raw_created.replace("Z", "+00:00")
                            )
                        except ValueError:
                            pass
                    task = asyncio.create_task(
                        service.upsert_viewer_profile_cache(
                            channel_id=channel_id,
                            user_id=user_id,
                            username=profile["username"],
                            display_name=profile.get("display_name"),
                            profile_image_url=profile_image_url,
                            offline_image_url=offline_image_url,
                            account_created_at=account_created_at,
                            broadcaster_type=broadcaster_type,
                        )
                    )
                    _background_tasks.add(task)
                    task.add_done_callback(_on_background_task_done)
            except Exception:
                LOGGER.warning("user_info fetch failed for %s", user_id, exc_info=True)

        twitch_status = ViewerTwitchStatus(
            is_subscribed=bool(status.get("is_subscribed", False)),
            sub_tier=status.get("sub_tier"),
            sub_gifted=status.get("sub_gifted"),
            sub_gifter=status.get("sub_gifter"),
            is_mod=bool(status.get("is_mod", False)),
            is_vip=bool(status.get("is_vip", False)),
            is_banned=bool(status.get("is_banned", False)),
            ban_expires_at=status.get("ban_expires_at"),
            ban_reason=status.get("ban_reason"),
        )

        session_attendance = [ViewerSessionAttendance(**r) for r in attendance_rows]

        response.headers["Cache-Control"] = "private, max-age=300"
        return ViewerProfile(
            twitch=twitch_status,
            profile_image_url=profile_image_url,
            offline_image_url=offline_image_url,
            account_created_at=account_created_at,
            broadcaster_type=broadcaster_type,
            session_attendance=session_attendance,
            **profile,
        )
    except HTTPException:
        raise
    except Exception:
        LOGGER.exception("Failed to get viewer profile")
        raise HTTPException(status_code=500, detail="Failed to fetch viewer") from None


@router.get("/channel/badges")
async def get_channel_badges(
    response: Response,
    channel_id: str = Depends(get_current_channel_id),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> ChannelBadgesResponse:
    badges = await twitch_api.get_channel_badges(channel_id)
    response.headers["Cache-Control"] = "private, max-age=3600"
    return ChannelBadgesResponse(**badges)


@router.get("/channel/badges/global")
async def get_global_badges(
    response: Response,
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> dict[str, list]:
    badges = await twitch_api.get_global_badges()
    response.headers["Cache-Control"] = "public, max-age=86400"
    return badges


class RoleSyncResult(BaseModel):
    mods_synced: int
    vips_synced: int
    subs_synced: int
    follows_synced: int = 0


@router.post("/sync-roles", response_model=RoleSyncResult)
async def sync_channel_roles(
    channel_id: str = Depends(get_current_channel_id),
    service: AnalyticsService = Depends(get_analytics_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
    pool: asyncpg.Pool = Depends(get_db_pool),
) -> RoleSyncResult:
    """Bulk-sync roles and follow dates from Twitch into viewer_channel_status."""
    from shared.repositories.channel import ChannelRepository

    token_row = await ChannelRepository(pool).get_token(channel_id)
    if not token_row:
        raise HTTPException(status_code=400, detail="No broadcaster token stored for this channel")

    token = token_row.token
    mods, vips, subs, followers = await asyncio.gather(
        twitch_api.fetch_all_moderators(channel_id, token),
        twitch_api.fetch_all_vips(channel_id, token),
        twitch_api.fetch_all_subscribers(channel_id, token),
        twitch_api.fetch_all_followers(channel_id, token),
    )
    LOGGER.info(
        "sync-roles: channel=%s mods=%d vips=%d subs=%d follows=%d",
        channel_id,
        len(mods),
        len(vips),
        len(subs),
        len(followers),
    )
    mod_count, vip_count, sub_count, follow_count = await asyncio.gather(
        service.bulk_upsert_mod_status(channel_id, mods),
        service.bulk_upsert_vip_status(channel_id, vips),
        service.bulk_upsert_subscribers(channel_id, subs),
        service.bulk_upsert_follow_dates(channel_id, followers),
    )
    return RoleSyncResult(
        mods_synced=mod_count,
        vips_synced=vip_count,
        subs_synced=sub_count,
        follows_synced=follow_count,
    )


@router.get("/top-commands", response_model=list[CommandStat])
async def get_top_commands(
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    channel_id: str = Depends(get_current_channel_id),
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[CommandStat]:
    try:
        commands = await service.get_top_commands(channel_id, days, limit)

        LOGGER.debug(f"Channel {channel_id} requested top commands (days={days}, limit={limit})")
        return [CommandStat(**cmd) for cmd in commands]

    except Exception:
        LOGGER.exception("Failed to get top commands")
        raise HTTPException(status_code=500, detail="Failed to fetch top commands") from None
