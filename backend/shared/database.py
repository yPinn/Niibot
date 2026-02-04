"""Unified database connection management for all Niibot services.

Supabase connection modes:
  - Session Pooler  (port 5432) : persistent servers, supports prepared statements
  - Transaction Pooler (port 6543) : serverless/edge, no prepared statement support
"""

import asyncio
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class PoolConfig:
    """Database pool configuration with sensible defaults."""

    min_size: int = 1
    max_size: int = 5
    timeout: float = 30.0
    command_timeout: float = 30.0
    max_inactive_connection_lifetime: float = 300.0
    max_retries: int = 3
    retry_delay: float = 5.0


class DatabaseManager:
    """Manages PostgreSQL connection pool lifecycle.

    Unified manager used by API, Twitch, and Discord services.
    Handles Supabase Transaction vs Session Pooler detection,
    retry logic, and proper lifecycle management.
    """

    def __init__(self, database_url: str, config: PoolConfig | None = None):
        self.database_url = database_url
        self.config = config or PoolConfig()
        self._pool: asyncpg.Pool | None = None

    @property
    def is_transaction_pooler(self) -> bool:
        """Detect Supabase Transaction Pooler by port 6543."""
        return ":6543" in self.database_url

    @property
    def statement_cache_size(self) -> int:
        """Transaction Pooler (6543) does not support prepared statements."""
        return 0 if self.is_transaction_pooler else 100

    async def connect(self) -> None:
        """Initialize database connection pool with retry."""
        if self._pool is not None:
            logger.warning("Database pool already initialized")
            return

        if self.is_transaction_pooler:
            logger.warning(
                "Using Transaction Pooler (6543) — "
                "consider switching to Session Pooler (5432) for persistent servers"
            )

        cfg = self.config
        for attempt in range(1, cfg.max_retries + 1):
            try:
                self._pool = await asyncpg.create_pool(
                    self.database_url,
                    min_size=cfg.min_size,
                    max_size=cfg.max_size,
                    timeout=cfg.timeout,
                    command_timeout=cfg.command_timeout,
                    ssl="require",
                    statement_cache_size=self.statement_cache_size,
                    max_inactive_connection_lifetime=cfg.max_inactive_connection_lifetime,
                )
                logger.info(
                    f"Database pool created "
                    f"(size={cfg.min_size}-{cfg.max_size}, cache={self.statement_cache_size})"
                )
                return
            except Exception as e:
                if attempt < cfg.max_retries:
                    logger.warning(
                        f"Database connection attempt {attempt}/{cfg.max_retries} failed: {e}, "
                        f"retrying in {cfg.retry_delay}s..."
                    )
                    await asyncio.sleep(cfg.retry_delay)
                else:
                    logger.exception(
                        f"Database connection failed after {cfg.max_retries} attempts: {e}"
                    )
                    raise

    async def disconnect(self) -> None:
        """Close database connection pool."""
        if self._pool is None:
            return

        try:
            await self._pool.close()
            self._pool = None
            logger.info("Database pool closed")
        except Exception as e:
            logger.exception(f"Error closing database pool: {e}")

    @property
    def pool(self) -> asyncpg.Pool:
        """Get the database connection pool. Raises if not initialized."""
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        return self._pool

    async def get_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Yield a connection from the pool (for dependency injection)."""
        async with self.pool.acquire() as conn:
            yield conn
