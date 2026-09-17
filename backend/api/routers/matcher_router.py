"""Matcher analytics API routes — audience overlap between home and partner channels."""

import asyncio
import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from core.dependencies import (
    get_analytics_service,
    get_current_channel_id,
    get_twitch_api,
)
from core.rate_limit import RateLimiter
from routers.analytics_router import InsightsGameStat
from services import AnalyticsService, TwitchAPIClient

LOGGER: logging.Logger = logging.getLogger(__name__)
_background_tasks: set[asyncio.Task] = set()

_matcher_refresh_limiter = RateLimiter(max_calls=1, period=1800.0)

router = APIRouter(prefix="/api/analytics/matcher", tags=["matcher"])


class MatcherChannelSummary(BaseModel):
    channel_id: str
    login: str | None = None
    display_name: str | None = None
    profile_image_url: str | None = None
    broadcaster_type: str | None = None
    description: str | None = None
    language: str | None = None
    tags: list[str] = []
    is_live: bool = False
    viewer_count: int = 0
    stream_title: str | None = None
    stream_game: str | None = None
    stream_thumbnail_url: str | None = None
    monitored_chatters: int
    shared_chatters: int
    exclusive_to_partner: int
    overlap_pct: float
    computed_at: datetime | None = None
    top_games: list[str] = []
    top_games_stats: list[InsightsGameStat] = []
    peak_hours: list[int] = []
    session_count: int = 0
    avg_stream_hours: float = 0.0
    channel_view_count: int | None = None


class PotentialViewer(BaseModel):
    user_id: str
    username: str
    display_name: str | None
    partner_sessions: int
    partner_messages: int
    partner_watch_sec: int
    partner_last_seen: datetime | None
    home_sessions: int
    home_messages: int
    potential_score: float


class MatcherViewersResponse(BaseModel):
    partner_channel_id: str
    total: int
    viewers: list[PotentialViewer]


class RefreshResult(BaseModel):
    refreshed_channels: int


class CreateCollabRequest(BaseModel):
    window_days: Annotated[int, Field(ge=1, le=365)] = 30
    note: str | None = None


class CollabEvent(BaseModel):
    id: int
    occurred_at: datetime
    note: str | None
    window_days: int
    target_count: int


class CollabConversion(BaseModel):
    id: int
    occurred_at: datetime
    note: str | None
    window_days: int
    target_count: int
    followed_count: int
    subscribed_count: int
    returned_count: int
    converted_any_count: int
    converted_pct: float
    attribution_ends_at: datetime


def _on_background_task_done(task: asyncio.Task) -> None:
    _background_tasks.discard(task)
    if not task.cancelled() and (exc := task.exception()):
        LOGGER.warning("Background matcher refresh failed: %s", exc)


@router.get("", response_model=list[MatcherChannelSummary])
async def get_matcher_summaries(
    response: Response,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    channel_id: str = Depends(get_current_channel_id),
    service: AnalyticsService = Depends(get_analytics_service),
    twitch_api: TwitchAPIClient = Depends(get_twitch_api),
) -> list[MatcherChannelSummary]:
    summaries = await service.get_matcher_summaries(channel_id, days)

    if not summaries:
        task = asyncio.create_task(service.refresh_matcher(channel_id, days))
        _background_tasks.add(task)
        task.add_done_callback(_on_background_task_done)
        response.headers["Cache-Control"] = "private, max-age=300"
        response.status_code = 202
        return []

    partner_ids = [s["partner_channel_id"] for s in summaries]

    users_list, streams_list, channels_list, session_stats_list = await asyncio.gather(
        twitch_api.get_users_by_ids(partner_ids),
        twitch_api.get_streams(partner_ids),
        twitch_api.get_channels_info(partner_ids),
        asyncio.gather(*[service.get_partner_session_stats(pid, 90) for pid in partner_ids]),
    )

    users_by_id: dict[str, dict] = {u["id"]: u for u in users_list}
    streams_by_id: dict[str, dict] = {s["user_id"]: s for s in streams_list}
    channels_by_id: dict[str, dict] = {c["broadcaster_id"]: c for c in channels_list}
    stats_by_id: dict[str, dict] = dict(zip(partner_ids, session_stats_list, strict=True))

    result: list[MatcherChannelSummary] = []
    for s in summaries:
        pid = s["partner_channel_id"]
        user = users_by_id.get(pid, {})
        stream = streams_by_id.get(pid, {})
        channel = channels_by_id.get(pid, {})
        stats = stats_by_id.get(pid, {})
        is_live = pid in streams_by_id
        result.append(
            MatcherChannelSummary(
                channel_id=pid,
                login=user.get("login"),
                display_name=user.get("display_name"),
                profile_image_url=user.get("profile_image_url"),
                broadcaster_type=user.get("broadcaster_type"),
                description=user.get("description") or None,
                language=channel.get("broadcaster_language") or None,
                tags=channel.get("tags") or [],
                is_live=is_live,
                viewer_count=int(stream.get("viewer_count", 0)) if is_live else 0,
                stream_title=stream.get("title") if is_live else None,
                stream_game=stream.get("game_name") if is_live else None,
                stream_thumbnail_url=stream.get("thumbnail_url") if is_live else None,
                monitored_chatters=s["partner_unique_chatters"],
                shared_chatters=s["shared_chatters"],
                exclusive_to_partner=s["exclusive_to_partner"],
                overlap_pct=float(s["overlap_pct"]),
                computed_at=s.get("computed_at"),
                top_games=stats.get("top_games", []),
                top_games_stats=[InsightsGameStat(**g) for g in stats.get("top_games_stats", [])],
                peak_hours=stats.get("peak_hours", []),
                session_count=stats.get("session_count", 0),
                avg_stream_hours=stats.get("avg_stream_hours", 0.0),
                channel_view_count=int(user["view_count"]) if user.get("view_count") else None,
            )
        )

    response.headers["Cache-Control"] = "private, max-age=300"
    return result


@router.get("/{partner_channel_id}/viewers", response_model=MatcherViewersResponse)
async def get_potential_viewers(
    partner_channel_id: str,
    response: Response,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    channel_id: str = Depends(get_current_channel_id),
    service: AnalyticsService = Depends(get_analytics_service),
) -> MatcherViewersResponse:
    total, viewers = await service.get_potential_viewers(
        channel_id, partner_channel_id, days, limit, offset
    )
    response.headers["Cache-Control"] = "private, max-age=300"
    return MatcherViewersResponse(
        partner_channel_id=partner_channel_id,
        total=total,
        viewers=[PotentialViewer(**v) for v in viewers],
    )


@router.post("/refresh", response_model=RefreshResult)
async def refresh_matcher(
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    channel_id: str = Depends(get_current_channel_id),
    service: AnalyticsService = Depends(get_analytics_service),
) -> RefreshResult:
    _matcher_refresh_limiter.require(channel_id)
    count = await service.refresh_matcher(channel_id, days)
    return RefreshResult(refreshed_channels=count)


@router.post("/{partner_channel_id}/collabs", response_model=CollabEvent)
async def create_collab_event(
    partner_channel_id: str,
    body: CreateCollabRequest,
    channel_id: str = Depends(get_current_channel_id),
    service: AnalyticsService = Depends(get_analytics_service),
) -> CollabEvent:
    result = await service.create_collab_event(
        channel_id, partner_channel_id, body.window_days, body.note
    )
    return CollabEvent(**result)


@router.get("/{partner_channel_id}/collabs", response_model=list[CollabConversion])
async def list_collab_events(
    partner_channel_id: str,
    channel_id: str = Depends(get_current_channel_id),
    service: AnalyticsService = Depends(get_analytics_service),
) -> list[CollabConversion]:
    results = await service.list_collab_events(channel_id, partner_channel_id)
    return [CollabConversion(**r) for r in results]


@router.delete("/{partner_channel_id}/collabs/{collab_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collab_event(
    partner_channel_id: str,
    collab_id: int,
    channel_id: str = Depends(get_current_channel_id),
    service: AnalyticsService = Depends(get_analytics_service),
) -> None:
    deleted = await service.delete_collab_event(channel_id, collab_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collab event not found")
