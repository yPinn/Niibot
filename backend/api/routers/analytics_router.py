"""Analytics API routes"""

import json
import logging
from datetime import datetime
from typing import Annotated

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
    total_bits: int


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


class ViewerProfile(BaseModel):
    user_id: str
    username: str
    display_name: str | None
    total_messages: int
    sessions_attended: int
    last_seen: datetime | None
    total_bits: int
    follow_since: datetime | None = None
    twitch: ViewerTwitchStatus | None = None
    events: list[ViewerEvent]


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
        LOGGER.info(f"Channel {channel_id} requested analytics summary (days={days})")
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

        twitch_status: ViewerTwitchStatus | None = None
        try:
            token = await channel_service.get_token_with_refresh(channel_id, twitch_api)
            if token:
                sub_data = await twitch_api.get_sub_status(channel_id, user_id, token)
                if sub_data:
                    raw_tier = sub_data.get("tier", "")
                    twitch_status = ViewerTwitchStatus(
                        is_subscribed=True,
                        sub_tier=_SUB_TIER_LABELS.get(raw_tier, raw_tier) or None,
                        sub_gifted=sub_data.get("is_gift", False),
                    )
                else:
                    twitch_status = ViewerTwitchStatus(is_subscribed=False)
        except Exception:
            LOGGER.warning(f"Twitch status fetch failed for viewer {user_id}")

        response.headers["Cache-Control"] = "private, max-age=300"
        return ViewerProfile(twitch=twitch_status, **profile)
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

        LOGGER.info(f"Channel {channel_id} requested top commands (days={days}, limit={limit})")
        return [CommandStat(**cmd) for cmd in commands]

    except Exception:
        LOGGER.exception("Failed to get top commands")
        raise HTTPException(status_code=500, detail="Failed to fetch top commands") from None
