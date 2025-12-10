"""資料庫連線服務

共用 Twitch Bot 的 PostgreSQL 資料庫
"""

import logging
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)

# 全域連線池
_pool: Optional[asyncpg.Pool] = None


async def get_database_pool() -> asyncpg.Pool:
    """取得資料庫連線池

    共用 Twitch Bot 的資料庫連線
    """
    global _pool

    if _pool is not None:
        return _pool

    # 從環境變數讀取資料庫 URL
    import os
    from pathlib import Path

    from dotenv import load_dotenv

    # Load environment variables from backend directory
    env_path = Path(__file__).parent.parent.parent / ".env"
    load_dotenv(dotenv_path=env_path)

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise ValueError("DATABASE_URL not found in environment variables")

    try:
        _pool = await asyncpg.create_pool(
            database_url,
            min_size=1,
            max_size=5,  # API server 不需要太多連線
            timeout=30.0,  # 增加 timeout 以應對遠端資料庫
            command_timeout=20.0  # 增加命令超時時間
        )
        logger.info("Database connection pool created successfully")
        return _pool

    except Exception as e:
        logger.exception(f"Failed to create database pool: {e}")
        raise


async def close_database_pool():
    """關閉資料庫連線池"""
    global _pool

    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")
