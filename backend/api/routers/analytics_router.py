"""Analytics API routes"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel

from core.dependencies import get_analytics_service, get_current_channel_id
from services import AnalyticsService

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


class StreamEvent(BaseModel):
    event_type: str
    user_id: str | None
    username: str | None
    display_name: str | None
    metadata: dict | None
    occurred_at: datetime


class AnalyticsSummary(BaseModel):
    total_sessions: int
    total_stream_hours: float
    total_commands: int
    total_follows: int
    total_subs: int
    avg_session_duration: float
    recent_sessions: list[SessionSummary]


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
