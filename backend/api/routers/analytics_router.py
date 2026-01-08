"""Analytics API routes"""

import logging
from datetime import datetime
from typing import List, Optional

from core.dependencies import get_analytics_service, get_current_user_id, get_db_pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


# ============================================
# Response Models
# ============================================


class SessionSummary(BaseModel):
    session_id: int
    channel_id: str
    started_at: datetime
    ended_at: Optional[datetime]
    title: Optional[str]
    game_name: Optional[str]
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
    user_id: Optional[str]
    username: Optional[str]
    display_name: Optional[str]
    metadata: Optional[dict]
    occurred_at: datetime


class AnalyticsSummary(BaseModel):
    total_sessions: int
    total_stream_hours: float
    total_commands: int
    total_follows: int
    total_subs: int
    avg_session_duration: float
    recent_sessions: List[SessionSummary]


# ============================================
# Endpoints
# ============================================


@router.get("/summary", response_model=AnalyticsSummary)
async def get_analytics_summary(
    days: int = 30,
    user_id: str = Depends(get_current_user_id),
) -> AnalyticsSummary:
    """
    Get analytics summary for the authenticated user

    Args:
        days: Number of days to look back (default: 30)
    """
    try:
        pool = await get_db_pool()
        analytics_service = get_analytics_service(pool)
        summary_data = await analytics_service.get_summary(user_id, days)

        logger.info(f"User {user_id} requested analytics summary (days={days})")
        return AnalyticsSummary(**summary_data)

    except Exception as e:
        logger.exception(f"Failed to get analytics summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch analytics")


@router.get("/sessions/{session_id}/commands", response_model=List[CommandStat])
async def get_session_commands(
    session_id: int,
    user_id: str = Depends(get_current_user_id),
) -> List[CommandStat]:
    """
    Get command statistics for a specific session

    Args:
        session_id: Session ID to query
    """
    try:
        pool = await get_db_pool()
        analytics_service = get_analytics_service(pool)
        commands = await analytics_service.get_session_commands(session_id, user_id)

        if commands is None:
            raise HTTPException(status_code=404, detail="Session not found")

        return [CommandStat(**cmd) for cmd in commands]

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get session commands: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch commands")


@router.get("/sessions/{session_id}/events", response_model=List[StreamEvent])
async def get_session_events(
    session_id: int,
    user_id: str = Depends(get_current_user_id),
) -> List[StreamEvent]:
    """
    Get events for a specific session

    Args:
        session_id: Session ID to query
    """
    try:
        pool = await get_db_pool()
        analytics_service = get_analytics_service(pool)
        events = await analytics_service.get_session_events(session_id, user_id)

        if events is None:
            raise HTTPException(status_code=404, detail="Session not found")

        return [StreamEvent(**event) for event in events]

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Failed to get session events: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch events")


@router.get("/top-commands", response_model=List[CommandStat])
async def get_top_commands(
    days: int = 30,
    limit: int = 10,
    user_id: str = Depends(get_current_user_id),
) -> List[CommandStat]:
    """
    Get top commands across all sessions

    Args:
        days: Number of days to look back (default: 30)
        limit: Maximum number of commands to return (default: 10)
    """
    try:
        pool = await get_db_pool()
        analytics_service = get_analytics_service(pool)
        commands = await analytics_service.get_top_commands(user_id, days, limit)

        logger.info(f"User {user_id} requested top commands (days={days}, limit={limit})")
        return [CommandStat(**cmd) for cmd in commands]

    except Exception as e:
        logger.exception(f"Failed to get top commands: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch top commands")
