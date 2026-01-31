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

            # 隱藏密碼的日誌
            safe_url = database_url.split("@")[-1] if "@" in database_url else "invalid"
            logger.info(f"Connecting to database: {safe_url}")

            try:
                # Supabase Transaction Pooler (6543) 需要禁用 prepared statements
                is_pooler = ":6543" in database_url or "pooler.supabase" in database_url

                cls._pool = await asyncpg.create_pool(
                    database_url,
                    min_size=1,
                    max_size=5,
                    command_timeout=30,
                    timeout=30,  # 連線建立超時
                    ssl="require",  # Supabase 需要 SSL
                    # Transaction Pooler 不支援 prepared statements
                    statement_cache_size=0 if is_pooler else 100,
                )
                logger.info(
                    f"Database connection pool created (pooler_mode={is_pooler})"
                )
            except Exception as e:
                logger.error(f"Database connection failed: {type(e).__name__}: {e}")
                raise

        return cls._pool

    @classmethod
    async def close(cls) -> None:
        """Close the connection pool."""
        if cls._pool is not None:
            await cls._pool.close()
            cls._pool = None
            logger.info("Database connection pool closed")
