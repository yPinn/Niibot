"""Database connection service"""

import logging
from typing import Optional

import asyncpg
from config import DATABASE_URL

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_database_pool() -> asyncpg.Pool:
    global _pool

    if _pool is not None:
        return _pool

    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not found in environment variables")

    try:
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=5,
            timeout=30.0,
            command_timeout=20.0,
            statement_cache_size=0
        )
        logger.info("Database connection pool created successfully")
        return _pool

    except Exception as e:
        logger.exception(f"Failed to create database pool: {e}")
        raise


async def close_database_pool():
    global _pool

    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Database connection pool closed")
