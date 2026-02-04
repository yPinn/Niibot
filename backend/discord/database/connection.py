"""Database connection pool management.

Supabase 連線模式:
  - Session Pooler  (port 5432) : 持久性伺服器推薦，支援 prepared statements
  - Transaction Pooler (port 6543) : serverless/edge 短暫連線用，不支援 prepared statements
"""

import asyncio
import logging
import os

import asyncpg

logger = logging.getLogger(__name__)


class DatabasePool:
    """Manages asyncpg connection pool for Supabase PostgreSQL (Session Pooler)."""

    _pool: asyncpg.Pool | None = None

    @classmethod
    async def get_pool(cls, max_retries: int = 3, retry_delay: float = 5.0) -> asyncpg.Pool:
        """Get or create the connection pool with retry."""
        if cls._pool is None:
            database_url = os.getenv("DATABASE_URL")
            if not database_url:
                raise ValueError("DATABASE_URL environment variable is not set")

            safe_url = database_url.split("@")[-1] if "@" in database_url else "invalid"
            logger.info(f"Connecting to database: {safe_url}")

            # Transaction Pooler (6543) 不支援 prepared statements
            # Session Pooler (5432) 或 Direct 可使用 prepared statements
            is_transaction_pooler = ":6543" in database_url
            cache_size = 0 if is_transaction_pooler else 100

            if is_transaction_pooler:
                logger.warning(
                    "Using Transaction Pooler (6543) — "
                    "consider switching to Session Pooler (5432) for persistent servers"
                )

            for attempt in range(1, max_retries + 1):
                try:
                    cls._pool = await asyncpg.create_pool(
                        database_url,
                        min_size=1,
                        max_size=5,
                        command_timeout=30,
                        timeout=30,
                        ssl="require",
                        statement_cache_size=cache_size,
                        max_inactive_connection_lifetime=300.0,
                    )
                    logger.info(f"Database pool created (cache={cache_size})")
                    break
                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(
                            f"Database connection attempt {attempt}/{max_retries} failed: {e}, "
                            f"retrying in {retry_delay}s..."
                        )
                        await asyncio.sleep(retry_delay)
                    else:
                        logger.exception(
                            f"Database connection failed after {max_retries} attempts: {e}"
                        )
                        raise

        return cls._pool

    @classmethod
    async def close(cls) -> None:
        """Close the connection pool."""
        if cls._pool is not None:
            await cls._pool.close()
            cls._pool = None
            logger.info("Database connection pool closed")
