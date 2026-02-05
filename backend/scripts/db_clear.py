"""Clear test session data from database"""

import asyncio
import sys
from pathlib import Path

import asyncpg

# Ensure backend/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.core.config import get_settings


async def clear_test_data():
    """Clear all test session data"""
    settings = get_settings()
    # Set statement_cache_size=0 for pgbouncer compatibility
    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0)

    try:
        # Delete all stream_events (foreign key constraint)
        events_count = await conn.fetchval("SELECT COUNT(*) FROM stream_events")
        await conn.execute("DELETE FROM stream_events")
        print(f"✓ Deleted {events_count} stream events")

        # Delete all command_stats (foreign key constraint)
        commands_count = await conn.fetchval("SELECT COUNT(*) FROM command_stats")
        await conn.execute("DELETE FROM command_stats")
        print(f"✓ Deleted {commands_count} command stats")

        # Delete all stream_sessions
        sessions_count = await conn.fetchval("SELECT COUNT(*) FROM stream_sessions")
        await conn.execute("DELETE FROM stream_sessions")
        print(f"✓ Deleted {sessions_count} stream sessions")

        print("\n✓ Successfully cleared all test data!")

    except Exception as e:
        print(f"✗ Failed to clear data: {e}")
        raise

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(clear_test_data())
