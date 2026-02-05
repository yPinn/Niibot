"""Generate test session data for development"""

import asyncio
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any  # 移除 dict, list 的匯入

# Ensure backend/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from api.core.config import get_settings


async def seed_test_sessions(channel_id: str | None = None):
    """為過去 30 天建立測試直播會話數據"""

    settings = get_settings()

    # 連接資料庫，禁用語句快取以相容 pgbouncer
    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0)

    try:
        # 若未提供 channel_id，從資料庫中獲取第一個頻道
        if not channel_id:
            row = await conn.fetchrow("SELECT channel_id FROM channels LIMIT 1")
            if row:
                channel_id = row["channel_id"]
                print(f"Using channel_id from database: {channel_id}")
            else:
                print("Error: No channels found in database.")
                return

        # 遊戲基礎數據
        games = [
            {"id": "509658", "name": "Just Chatting"},
            {"id": "21779", "name": "League of Legends"},
            {"id": "516575", "name": "VALORANT"},
            {"id": "27471", "name": "Minecraft"},
            {"id": "511224", "name": "Apex Legends"},
            {"id": "32982", "name": "Grand Theft Auto V"},
            {"id": "33214", "name": "Fortnite"},
            {"id": "32399", "name": "Counter-Strike"},
            {"id": "29595", "name": "Dota 2"},
            {"id": "488552", "name": "Overwatch 2"},
        ]

        titles = [
            "Chill stream with chat",
            "Learning new strategies",
            "Ranked grind!",
            "Viewer games!",
            "Road to Masters",
            "Community event",
            "Practice session",
            "Late night vibes",
            "Morning coffee stream",
            "Weekend marathon",
        ]

        # 隨機生成 15-20 筆會話
        num_sessions = random.randint(15, 20)
        now = datetime.now()

        # 修正：直接使用內建 list 和 dict 標註類型
        sessions: list[dict[str, Any]] = []

        for _ in range(num_sessions):
            days_ago = random.randint(0, 29)
            hour = random.choices(
                range(24),
                weights=[
                    1,
                    1,
                    1,
                    1,
                    1,
                    1,
                    2,
                    3,
                    4,
                    5,
                    6,
                    7,
                    8,
                    9,
                    10,
                    11,
                    12,
                    10,
                    8,
                    6,
                    5,
                    4,
                    3,
                    2,
                ],
                k=1,
            )[0]

            started_at = now - timedelta(days=days_ago, hours=hour, minutes=random.randint(0, 59))
            duration_hours = round(random.uniform(1.0, 6.0), 2)
            ended_at = started_at + timedelta(hours=duration_hours)
            game = random.choice(games)

            sessions.append(
                {
                    "channel_id": channel_id,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "title": random.choice(titles),
                    "game_id": game["id"],
                    "game_name": game["name"],
                    "duration_hours": duration_hours,
                    "total_commands": random.randint(50, 500),
                    "new_follows": random.randint(0, 25),
                    "new_subs": random.randint(0, 10),
                    "raids_received": random.randint(0, 3),
                }
            )

        # 排序
        sessions.sort(key=lambda x: x["started_at"])

        # 寫入資料庫
        for s in sessions:
            result = await conn.fetchrow(
                """
                INSERT INTO stream_sessions
                    (channel_id, started_at, ended_at, title, game_id, game_name)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                s["channel_id"],
                s["started_at"],
                s["ended_at"],
                s["title"],
                s["game_id"],
                s["game_name"],
            )
            print(f"Created session {result['id']}: {s['title']} ({s['game_name']})")

        print(f"\nSuccessfully created {len(sessions)} test sessions!")

    finally:
        await conn.close()


if __name__ == "__main__":
    # 支援命令行參數
    cli_channel_id: str | None = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(seed_test_sessions(cli_channel_id))
