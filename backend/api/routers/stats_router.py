"""Channel statistics API routes"""

import logging

from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.dependencies import get_current_channel_id, get_db_pool
from shared.repositories.analytics import AnalyticsRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stats", tags=["stats"])


class CommandStat(BaseModel):
    name: str
    count: int


class ChatterStat(BaseModel):
    username: str
    message_count: int


class ChannelStats(BaseModel):
    top_commands: list[CommandStat]
    top_chatters: list[ChatterStat]
    total_messages: int
    total_commands: int


@router.get("/channel")
async def get_channel_stats(
    channel_id: str = Depends(get_current_channel_id),
    pool: Pool = Depends(get_db_pool),
) -> ChannelStats:
    """Get channel statistics"""
    try:
        repo = AnalyticsRepository(pool)

        top_chatters_data = await repo.list_top_chatters(channel_id, days=30, limit=10)
        top_commands_data = await repo.list_top_commands(channel_id, days=30, limit=10)
        total_messages = await repo.get_total_messages(channel_id, days=30)

        top_chatters = [
            ChatterStat(username=c["username"], message_count=c["message_count"])
            for c in top_chatters_data
        ]
        top_commands = [
            CommandStat(name=c["command_name"], count=c["usage_count"]) for c in top_commands_data
        ]
        total_commands = sum(cmd.count for cmd in top_commands)

        logger.info(f"Channel {channel_id} requested channel stats")
        return ChannelStats(
            top_commands=top_commands[:5],
            top_chatters=top_chatters[:5],
            total_messages=total_messages,
            total_commands=total_commands,
        )

    except Exception as e:
        logger.exception(f"Failed to get channel stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch statistics") from None
