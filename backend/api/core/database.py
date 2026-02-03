"""Database connection management with dependency injection support.

Supabase 連線模式:
  - Session Pooler  (port 5432) : 持久性伺服器推薦，支援 prepared statements
  - Transaction Pooler (port 6543) : serverless/edge 短暫連線用，不支援 prepared statements
"""

import logging
from collections.abc import AsyncGenerator

import asyncpg

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages PostgreSQL connection pool lifecycle"""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Initialize database connection pool"""
        if self._pool is not None:
            logger.warning("Database pool already initialized")
            return

        try:
            # Transaction Pooler (6543) 不支援 prepared statements
            # Session Pooler (5432) 或 Direct 可使用 prepared statements
            is_transaction_pooler = ":6543" in self.database_url
            cache_size = 0 if is_transaction_pooler else 100

            if is_transaction_pooler:
                logger.warning(
                    "Using Transaction Pooler (6543) — "
                    "consider switching to Session Pooler (5432) for persistent servers"
                )

            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=5,
                timeout=30.0,
                command_timeout=60.0,
                ssl="require",
                statement_cache_size=cache_size,
                max_inactive_connection_lifetime=300.0,
            )
            logger.info(f"Database pool created (cache={cache_size})")
        except Exception as e:
            logger.exception(f"Failed to create database pool: {e}")
            raise

    async def disconnect(self) -> None:
        """Close database connection pool"""
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
        """Get the database connection pool"""
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        return self._pool

    async def get_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Get a database connection from the pool (for dependency injection)"""
        async with self.pool.acquire() as conn:
            yield conn


# Global database manager instance
_db_manager: DatabaseManager | None = None


def get_database_manager() -> DatabaseManager:
    """Get the global database manager instance"""
    if _db_manager is None:
        raise RuntimeError("Database manager not initialized")
    return _db_manager


def init_database_manager(database_url: str) -> DatabaseManager:
    """Initialize the global database manager"""
    global _db_manager
    _db_manager = DatabaseManager(database_url)
    return _db_manager
