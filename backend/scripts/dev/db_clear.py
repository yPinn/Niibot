"""Clear all analytics / session data from database (dev / reset use only).

WARNING: Deletes stream_sessions and every dependent table.
         Do NOT run against production data.
         For production backfill, use scripts/tw_backfill_sessions.py instead.

Tables cleared (FK-safe order):
  stream_events, chatter_stats, command_stats,
  viewer_attendance_streaks, stream_sessions,
  viewer_channel_status,
  channel_overlap_viewers, channel_overlap_summary
"""

import asyncio
import sys
from pathlib import Path

import asyncpg

# Force UTF-8 stdout/stderr so Unicode symbols print correctly on Windows.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from api.core.config import get_settings


async def clear_test_data() -> None:
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0)

    try:
        # Delete in FK-dependency order so no constraint violations occur.
        steps: list[tuple[str, str]] = [
            ("stream_events", "stream events"),
            ("chatter_stats", "chatter stats"),
            ("command_stats", "command stats"),
            ("viewer_attendance_streaks", "attendance streaks"),
            ("stream_sessions", "stream sessions"),
            ("viewer_channel_status", "viewer channel status"),
            ("channel_overlap_viewers", "overlap viewers"),
            ("channel_overlap_summary", "overlap summary"),
        ]

        for table, label in steps:
            n = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
            await conn.execute(f"DELETE FROM {table}")  # noqa: S608
            print(f"  ✓ Deleted {n:>6} rows  ←  {label}")

        print("\n✓ All analytics data cleared.")

    except Exception as e:
        print(f"✗ Failed: {e}")
        raise

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(clear_test_data())
