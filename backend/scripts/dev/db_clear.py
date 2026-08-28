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

import argparse
import asyncio
import sys
from pathlib import Path

import asyncpg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _lib import confirm, load_env, utf8_stdio  # noqa: E402

utf8_stdio()

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from api.core.config import get_settings  # noqa: E402


async def clear_test_data() -> None:
    load_env("prod")
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="[dev] wipe analytics / session tables.")
    parser.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
    return parser


def run(args: argparse.Namespace) -> int:
    if not confirm(
        "Delete ALL analytics/session data (stream_sessions + dependents)?",
        getattr(args, "yes", False),
    ):
        print("Aborted.")
        return 0
    asyncio.run(clear_test_data())
    return 0


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
