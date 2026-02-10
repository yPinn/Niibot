"""Database connection management — delegates to shared module.

Thin wrapper that preserves the existing get_database_manager() / init_database_manager()
API so that app.py, dependencies.py, and all routers continue to work without changes.
"""

from shared.database import DatabaseManager, PoolConfig

# Global database manager instance
_db_manager: DatabaseManager | None = None


def get_database_manager() -> DatabaseManager:
    """Get the global database manager instance"""
    if _db_manager is None:
        raise RuntimeError("Database manager not initialized")
    return _db_manager


def init_database_manager(database_url: str) -> DatabaseManager:
    """Initialize database manager for API service (high concurrency)"""
    global _db_manager
    _db_manager = DatabaseManager(
        database_url,
        PoolConfig(
            min_size=3,
            max_size=15,
            timeout=60.0,
            command_timeout=60.0,
            max_inactive_connection_lifetime=180.0,
            max_retries=5,
            retry_delay=5.0,
            tcp_keepalives_idle=60,
            tcp_keepalives_interval=10,
            tcp_keepalives_count=5,
            health_check_interval=30,
        ),
    )
    return _db_manager
