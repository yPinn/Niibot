"""Analytics API routes"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, field_validator

from core.dependencies import (
    get_analytics_service,
    get_channel_service,
    get_current_channel_id,
    get_twitch_api,
)
from services import AnalyticsService, ChannelService, TwitchAPIClient

LOGGER: logging.Logger = logging.getLogger(__name__)

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
    total_subs: int
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
    engagement_score: float


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
    bits_rank: int | None = None


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
    follow_since: datetime | None = None
    streak_count: int = 0
    twitch: ViewerTwitchStatus | None = None
    events: list[ViewerEvent]
    session_attendance: list[ViewerSessionAttendance] = []


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


_SUB_TIER_LABELS = {"1000": "1", "2000": "2", "3000": "3"}


# Sentinel: Twitch API call failed — fall back to DB value
class _Unchecked:
    pass


_UNCHECKED = _Unchecked()


@router.get("/viewers/{user_id}", response_model=ViewerProfile)
async def get_viewer_profile(
    user_id: str,
    response: Response,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    channel_id: str = Depends(get_current_channel_id),
    service: AnalyticsService = Depends(get_analytics_service),
    channel_service: ChannelService = Depends(get_channel_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> ViewerProfile:
    try:
        profile = await service.get_viewer_profile(channel_id, user_id, days)
        if profile is None:
            raise HTTPException(status_code=404, detail="Viewer not found")

        # Get broadcaster token once; shared by sub + follow checks
        token: str | None = None
        try:
            token = await channel_service.get_token_with_refresh(channel_id, twitch_api)
        except Exception:
            LOGGER.warning("Token fetch failed for viewer profile")

        async def _fetch_sub() -> tuple[bool, str | None, bool | None, str | None]:
            """Returns (is_subscribed, sub_tier, sub_gifted, sub_gifter)."""
            if not token:
                return False, None, None, None
            try:
                sub_data = await twitch_api.get_sub_status(channel_id, user_id, token)
                if sub_data:
                    raw_tier = sub_data.get("tier", "")
                    is_gift = sub_data.get("is_gift", False)
                    gifter = sub_data.get("gifter_login") or None if is_gift else None
                    return (
                        True,
                        _SUB_TIER_LABELS.get(raw_tier, raw_tier) or None,
                        is_gift,
                        gifter,
                    )
                return False, None, None, None
            except Exception:
                LOGGER.warning(f"Sub status fetch failed for viewer {user_id}")
                return False, None, None, None

        async def _fetch_follow() -> datetime | None | _Unchecked:
            """Returns datetime | None (confirmed), or _UNCHECKED (API failed)."""
            if not token:
                return _UNCHECKED
            try:
                follow_data = await twitch_api.get_follow_status(channel_id, user_id, token)
                if follow_data:
                    raw = follow_data.get("followed_at", "")
                    try:
                        return datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None
                    except ValueError:
                        return None
                return None
            except Exception:
                LOGGER.warning(f"Follow status fetch failed for viewer {user_id}")
                return _UNCHECKED

        async def _fetch_user_info() -> dict | None:
            try:
                return await twitch_api.get_user_info(user_id)
            except Exception:
                return None

        async def _fetch_mod() -> bool:
            if not token:
                return False
            return await twitch_api.get_mod_status(channel_id, user_id, token)

        async def _fetch_vip() -> bool:
            if not token:
                return False
            return await twitch_api.get_vip_status(channel_id, user_id, token)

        async def _fetch_ban() -> dict | None:
            if not token:
                return None
            return await twitch_api.get_ban_status(channel_id, user_id, token)

        async def _fetch_bits_rank() -> int | None:
            if not token:
                return None
            return await twitch_api.get_bits_rank(user_id, token)

        async def _fetch_attendance() -> list[dict]:
            return await service.get_viewer_session_attendance(channel_id, user_id, days)

        _gathered = await asyncio.gather(
            _fetch_sub(),
            _fetch_follow(),
            _fetch_user_info(),
            _fetch_mod(),
            _fetch_vip(),
            _fetch_ban(),
            _fetch_bits_rank(),
            _fetch_attendance(),
        )
        sub_result = cast(tuple[bool, str | None, bool | None, str | None], _gathered[0])
        follow_api = cast(datetime | None | _Unchecked, _gathered[1])
        user_info = cast(dict[str, Any] | None, _gathered[2])
        is_mod = cast(bool, _gathered[3])
        is_vip = cast(bool, _gathered[4])
        ban_info = cast(dict[str, Any] | None, _gathered[5])
        bits_rank = cast(int | None, _gathered[6])
        attendance_rows = cast(list[dict], _gathered[7])

        # Follow date: use API result; fall back to DB only when API call failed
        follow_since = profile.get("follow_since") if follow_api is _UNCHECKED else follow_api
        profile["follow_since"] = follow_since

        # User info fields
        profile_image_url: str | None = user_info.get("avatar") if user_info else None
        offline_image_url: str | None = (
            (user_info.get("offline_image_url") or None) if user_info else None
        )
        broadcaster_type: str | None = (
            (user_info.get("broadcaster_type") or None) if user_info else None
        )
        account_created_at: datetime | None = None
        if user_info and user_info.get("account_created_at"):
            try:
                account_created_at = datetime.fromisoformat(
                    user_info["account_created_at"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # Ban date parsing
        ban_expires_at: datetime | None = None
        if ban_info and ban_info.get("expires_at"):
            try:
                ban_expires_at = datetime.fromisoformat(
                    ban_info["expires_at"].replace("Z", "+00:00")
                )
            except ValueError:
                pass

        is_subscribed, sub_tier, sub_gifted, sub_gifter = sub_result
        twitch_status = ViewerTwitchStatus(
            is_subscribed=is_subscribed,
            sub_tier=sub_tier,
            sub_gifted=sub_gifted,
            sub_gifter=sub_gifter,
            is_mod=is_mod,
            is_vip=is_vip,
            is_banned=bool(ban_info),
            ban_expires_at=ban_expires_at,
            ban_reason=ban_info.get("reason") if ban_info else None,
            bits_rank=bits_rank,
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
