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
    """Initialize the global database manager"""
    global _db_manager
    _db_manager = DatabaseManager(database_url, PoolConfig(min_size=1, max_size=5))
    return _db_manager
