"""Channel statistics API routes"""

import logging
import random
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.dependencies import get_current_user_id

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


# Mock data
MOCK_COMMANDS = [
    CommandStat(name="!commands", count=156),
    CommandStat(name="!ai", count=89),
    CommandStat(name="!運勢", count=67),
    CommandStat(name="!help", count=45),
    CommandStat(name="!測試", count=34),
    CommandStat(name="!cmonbruh", count=28),
    CommandStat(name="!socials", count=23),
    CommandStat(name="!discord", count=19),
    CommandStat(name="!info", count=12),
    CommandStat(name="!uptime", count=8),
]

MOCK_CHATTERS = [
    ChatterStat(username="user1", message_count=487),
    ChatterStat(username="user2", message_count=356),
    ChatterStat(username="user3", message_count=298),
    ChatterStat(username="user4", message_count=245),
    ChatterStat(username="user5", message_count=189),
    ChatterStat(username="user6", message_count=167),
    ChatterStat(username="user7", message_count=134),
]


@router.get("/channel")
async def get_channel_stats(user_id: str = Depends(get_current_user_id)) -> ChannelStats:
    """Get channel statistics"""
    try:
        # TODO: Replace with actual database queries
        seed = datetime.now().minute
        random.seed(seed)

        def randomize_count(count: int) -> int:
            variation = random.randint(-5, 5) / 100
            return max(1, int(count * (1 + variation)))

        top_commands = [
            CommandStat(name=cmd.name, count=randomize_count(cmd.count))
            for cmd in MOCK_COMMANDS[:10]
        ]

        top_chatters = [
            ChatterStat(
                username=chatter.username, message_count=randomize_count(chatter.message_count)
            )
            for chatter in MOCK_CHATTERS[:10]
        ]

        total_commands = sum(cmd.count for cmd in top_commands)
        total_messages = sum(chatter.message_count for chatter in top_chatters) + random.randint(
            500, 800
        )

        logger.info(f"User {user_id} requested channel stats")
        return ChannelStats(
            top_commands=top_commands[:5],
            top_chatters=top_chatters[:5],
            total_messages=total_messages,
            total_commands=total_commands,
        )

    except Exception as e:
        logger.exception(f"Failed to get channel stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch statistics") from None
