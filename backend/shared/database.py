"""Unified database connection management for all Niibot services.

Supabase connection modes:
  - Session Pooler  (port 5432) : persistent servers, supports prepared statements
  - Transaction Pooler (port 6543) : serverless/edge, no prepared statement support
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass, fields
from typing import ClassVar

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class PoolConfig:
    """Database pool configuration with sensible defaults."""

    min_size: int = 1
    max_size: int = 5
    timeout: float = 30.0
    command_timeout: float = 30.0
    max_inactive_connection_lifetime: float = 60.0
    max_retries: int = 3
    retry_delay: float = 5.0

    # Keep-alive 設定
    tcp_keepalives_idle: int = 30
    tcp_keepalives_interval: int = 10
    tcp_keepalives_count: int = 3
    health_check_interval: int = 30

    # 各服務預設差異值
    _SERVICE_PRESETS: ClassVar[dict[str, dict]] = {
        "api": {"min_size": 2, "max_size": 10, "max_retries": 5},
        "discord": {"min_size": 1, "max_size": 4, "max_retries": 5},
        "twitch": {"min_size": 1, "max_size": 5, "max_retries": 5},
    }

    @classmethod
    def for_service(cls, service: str, **overrides) -> PoolConfig:
        """Create a PoolConfig with service-specific presets.

        Shared defaults (timeout, keepalive, etc.) come from the dataclass
        defaults. Only pool sizing / retry differ per service.
        """
        valid_keys = {f.name for f in fields(cls) if not f.name.startswith("_")}
        preset = dict(cls._SERVICE_PRESETS.get(service, {}))
        preset.update(overrides)
        filtered = {k: v for k, v in preset.items() if k in valid_keys}
        return cls(**filtered)


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
        self._health_check_task: asyncio.Task | None = None

    @property
    def is_transaction_pooler(self) -> bool:
        """Detect Supabase Transaction Pooler by port 6543."""
        return ":6543" in self.database_url

    @property
    def statement_cache_size(self) -> int:
        """Transaction Pooler (6543) does not support prepared statements."""
        return 0 if self.is_transaction_pooler else 100

    async def _init_connection(self, conn: asyncpg.Connection) -> None:
        """Initialize new connections (called automatically by pool)."""
        # 設定連線層級的 statement timeout
        timeout_ms = int(self.config.command_timeout * 1000)
        await conn.execute(f"SET statement_timeout = {timeout_ms}")

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
                    server_settings={
                        "tcp_keepalives_idle": str(cfg.tcp_keepalives_idle),
                        "tcp_keepalives_interval": str(cfg.tcp_keepalives_interval),
                        "tcp_keepalives_count": str(cfg.tcp_keepalives_count),
                    },
                    init=self._init_connection,
                )

                # 驗證 pool 可用性
                async with self._pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")

                logger.info(
                    f"Database pool created and verified "
                    f"(size={cfg.min_size}-{cfg.max_size}, cache={self.statement_cache_size}, "
                    f"keepalive={cfg.tcp_keepalives_idle}s)"
                )

                self._health_check_task = asyncio.create_task(self._pool_health_check())

                return
            except Exception as e:
                if attempt < cfg.max_retries:
                    logger.warning(
                        f"Database connection attempt {attempt}/{cfg.max_retries} failed: {e}, "
                        f"retrying in {cfg.retry_delay}s..."
                    )
                    # 清理失敗的 pool
                    if self._pool:
                        try:
                            await self._pool.close()
                        except Exception:
                            pass
                        self._pool = None
                    await asyncio.sleep(cfg.retry_delay)
                else:
                    logger.exception(
                        f"Database connection failed after {cfg.max_retries} attempts: {e}"
                    )
                    raise

    async def _pool_health_check(self) -> None:
        """定期檢查 pool 健康狀態,保持連線活躍"""
        interval = self.config.health_check_interval
        while True:
            try:
                await asyncio.sleep(interval)
                if self._pool:
                    async with self._pool.acquire() as conn:
                        await conn.fetchval("SELECT 1")
                    logger.debug(f"Database pool health check OK (interval={interval}s)")
            except asyncio.CancelledError:
                logger.info("Pool health check task cancelled")
                break
            except Exception as e:
                logger.error(f"Pool health check failed: {e}")
                if self._pool:
                    try:
                        self._pool.expire_connections()
                        logger.info("Expired all pool connections for refresh")
                    except Exception:
                        pass

    async def disconnect(self) -> None:
        """Close database connection pool."""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

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
