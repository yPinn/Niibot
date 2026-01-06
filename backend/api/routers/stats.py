"""Channel statistics API routes"""

import logging
import random
from datetime import datetime

from fastapi import APIRouter, Cookie, HTTPException
from pydantic import BaseModel
from services import auth as auth_service

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


# Mock data - 可以根據需要調整這些數據
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
    ChatterStat(username="皮先森♡", message_count=487),
    ChatterStat(username="fen1614", message_count=356),
    ChatterStat(username="오빠수프베어", message_count=298),
    ChatterStat(username="酥烤貓", message_count=245),
    ChatterStat(username="Niibot_", message_count=189),
    ChatterStat(username="酷烤貓", message_count=167),
    ChatterStat(username="meitoo85", message_count=134),
    ChatterStat(username="viewer123", message_count=98),
    ChatterStat(username="chatbot_friend", message_count=76),
    ChatterStat(username="stream_fan", message_count=54),
]


@router.get("/channel")
async def get_channel_stats(auth_token: str | None = Cookie(None)) -> ChannelStats:
    """Get channel statistics including top commands and chatters"""
    if not auth_token:
        raise HTTPException(status_code=401, detail="Not logged in")

    user_id = auth_service.verify_token(auth_token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    try:
        # TODO: Replace with actual database queries
        # For now, return mock data with slight randomization to simulate real-time changes

        # 添加一些隨機變化讓數據看起來更真實
        seed = datetime.now().minute  # 使用當前分鐘作為種子，每分鐘數據會略有不同
        random.seed(seed)

        # 隨機調整數據（±5%）
        def randomize_count(count: int) -> int:
            variation = random.randint(-5, 5) / 100
            return max(1, int(count * (1 + variation)))

        top_commands = [
            CommandStat(name=cmd.name, count=randomize_count(cmd.count))
            for cmd in MOCK_COMMANDS[:10]  # 只取前10個
        ]

        top_chatters = [
            ChatterStat(username=chatter.username, message_count=randomize_count(chatter.message_count))
            for chatter in MOCK_CHATTERS[:10]
        ]

        total_commands = sum(cmd.count for cmd in top_commands)
        total_messages = sum(chatter.message_count for chatter in top_chatters) + random.randint(500, 800)

        return ChannelStats(
            top_commands=top_commands[:5],  # 只返回前5個給 Dashboard
            top_chatters=top_chatters[:5],  # 只返回前5個給 Dashboard
            total_messages=total_messages,
            total_commands=total_commands,
        )

    except Exception as e:
        logger.exception(f"Failed to get channel stats: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch statistics")
