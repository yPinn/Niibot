"""Database connection pool management."""

import logging
import os

import asyncpg

logger = logging.getLogger(__name__)


class DatabasePool:
    """Manages asyncpg connection pool for Supabase PostgreSQL."""

    _pool: asyncpg.Pool | None = None

    @classmethod
    async def get_pool(cls) -> asyncpg.Pool:
        """Get or create the connection pool."""
        if cls._pool is None:
            database_url = os.getenv("SUPABASE_URL")
            if not database_url:
                raise ValueError("SUPABASE_URL environment variable is not set")

            cls._pool = await asyncpg.create_pool(
                database_url,
                min_size=1,
                max_size=5,
                command_timeout=30,
                timeout=30,  # 連線建立超時
                ssl="require",  # Supabase 需要 SSL
            )
            logger.info("Database connection pool created")

        return cls._pool

    @classmethod
    async def close(cls) -> None:
        """Close the connection pool."""
        if cls._pool is not None:
            await cls._pool.close()
            cls._pool = None
            logger.info("Database connection pool closed")
