"""Channel statistics API routes"""

import asyncio
import logging
from typing import Annotated

from asyncpg import Pool
from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from core.dependencies import get_current_channel_id, get_db_pool
from shared.repositories.analytics import AnalyticsRepository

LOGGER: logging.Logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stats", tags=["stats"])


class CommandStat(BaseModel):
    name: str
    count: int


class ChatterStat(BaseModel):
    username: str
    display_name: str | None = None
    message_count: int


class ChannelStats(BaseModel):
    top_commands: list[CommandStat]
    top_chatters: list[ChatterStat]
    total_messages: int
    total_commands: int


@router.get("/channel")
async def get_channel_stats(
    response: Response,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> ChannelStats:
    """Get channel statistics.

    top_commands: from command_configs.usage_count — session-independent, always available.
    top_chatters: from chatter_stats — aggregated from completed stream sessions.
    """
    repo = AnalyticsRepository(pool)

    top_chatters_data, top_commands_data, total_messages, total_commands = await asyncio.gather(
        repo.list_top_chatters(channel_id, days=days, limit=10),
        repo.list_top_commands_from_config(channel_id, days=days, limit=10),
        repo.get_total_messages(channel_id, days=days),
        repo.get_total_commands_from_config(channel_id, days=days),
    )

    top_chatters = [
        ChatterStat(
            username=c["username"],
            display_name=c.get("display_name"),
            message_count=c["message_count"],
        )
        for c in top_chatters_data
    ]
    top_commands = [
        CommandStat(name=c["command_name"], count=c["usage_count"]) for c in top_commands_data
    ]

    response.headers["Cache-Control"] = "private, max-age=300"
    LOGGER.debug("channel_stats_requested", extra={"days": days})
    return ChannelStats(
        top_commands=top_commands,
        top_chatters=top_chatters,
        total_messages=total_messages,
        total_commands=total_commands,
    )
