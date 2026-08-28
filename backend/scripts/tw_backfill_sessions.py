"""Backfill stream sessions from Twitch VODs (real historical data).

This script:
1. Clears existing test/fake session data
2. Fetches real VODs from Twitch API for each enabled channel
3. Creates session records from the VOD data

    python scripts/tw_backfill_sessions.py [--keep-existing] [--limit N]
    npm run nb -- twitch backfill-sessions --limit 50
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

import asyncpg

# backend/ + backend/api on sys.path — api.services.twitch_api re-imports
# `services._twitch_api...` internally, which needs backend/api/ too.
_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_BACKEND / "api"))

from _lib import add_env_arg, load_env  # noqa: E402
from api.core.config import get_settings  # noqa: E402
from api.services.twitch_api import TwitchAPIClient  # noqa: E402


async def clear_existing_sessions(conn: asyncpg.Connection) -> None:
    """Clear all existing session data."""
    print("\n[1/3] Clearing existing session data...")

    events_count = await conn.fetchval("SELECT COUNT(*) FROM stream_events")
    await conn.execute("DELETE FROM stream_events")
    print(f"  [OK] Deleted {events_count} stream events")

    commands_count = await conn.fetchval("SELECT COUNT(*) FROM command_stats")
    await conn.execute("DELETE FROM command_stats")
    print(f"  [OK] Deleted {commands_count} command stats")

    sessions_count = await conn.fetchval("SELECT COUNT(*) FROM stream_sessions")
    await conn.execute("DELETE FROM stream_sessions")
    print(f"  [OK] Deleted {sessions_count} stream sessions")


async def backfill_sessions(keep_existing: bool = False, limit: int = 20) -> None:
    """Main backfill function."""
    settings = get_settings()

    print("=" * 50)
    print("Twitch VOD Session Backfill")
    print("=" * 50)

    if not settings.client_id or not settings.client_secret:
        print("[X] Missing CLIENT_ID or CLIENT_SECRET in settings")
        return

    twitch = TwitchAPIClient(
        client_id=settings.client_id,
        client_secret=settings.client_secret,
        api_url=settings.api_url,
    )

    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0)

    try:
        # Verify Twitch API access
        print("\n[0/3] Authenticating with Twitch API...")
        token = await twitch._ensure_app_token()
        if not token:
            print("[X] Failed to get app access token")
            return
        print("  [OK] Got app access token")

        # Clear existing data if requested
        if not keep_existing:
            await clear_existing_sessions(conn)
        else:
            print("\n[1/3] Keeping existing sessions (--keep-existing)")

        # Get enabled channels
        print("\n[2/3] Fetching enabled channels...")
        channels = await conn.fetch(
            "SELECT channel_id, channel_name FROM channels WHERE enabled = TRUE"
        )
        print(f"  [OK] Found {len(channels)} enabled channels")

        if not channels:
            print("  [!] No enabled channels found. Nothing to backfill.")
            return

        # Fetch VODs for each channel
        print(f"\n[3/3] Fetching VODs (limit: {limit} per channel)...")
        total_sessions = 0

        for channel in channels:
            channel_id = channel["channel_id"]
            channel_name = channel["channel_name"]
            print(f"\n  > Channel: {channel_name} ({channel_id})")

            videos = await twitch.get_videos(channel_id, video_type="archive", first=limit)
            if not videos:
                print("    No VODs found (channel may not have VODs enabled)")
                continue

            print(f"    Found {len(videos)} VODs")

            for video in videos:
                title = video.get("title", "Untitled")
                created_at_str = video.get("created_at")
                duration_str = video.get("duration", "0s")

                if not created_at_str:
                    continue

                started_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                duration_hours = TwitchAPIClient.parse_duration(duration_str)
                ended_at = started_at + timedelta(hours=duration_hours)

                # Check for duplicates (by started_at and channel_id)
                existing = await conn.fetchrow(
                    """
                    SELECT id FROM stream_sessions
                    WHERE channel_id = $1 AND started_at = $2
                    """,
                    channel_id,
                    started_at,
                )
                if existing:
                    print(f"    [-] Skipping duplicate: {title[:30]}...")
                    continue

                # Insert session
                result = await conn.fetchrow(
                    """
                    INSERT INTO stream_sessions
                        (channel_id, started_at, ended_at, title, game_name, game_id)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    RETURNING id
                    """,
                    channel_id,
                    started_at,
                    ended_at,
                    title,
                    None,  # game_name (VODs may have multiple games)
                    None,  # game_id
                )
                session_id = result["id"]
                total_sessions += 1
                print(f"    [OK] [{session_id}] {title[:40]}... ({duration_str})")

        print("\n" + "=" * 50)
        print(f"[OK] Successfully created {total_sessions} sessions from VODs!")
        print("=" * 50)

    except Exception as e:
        print(f"\n[X] Error: {e}")
        raise

    finally:
        await twitch.close()
        await conn.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill stream sessions from Twitch VODs.")
    parser.add_argument("--keep-existing", action="store_true", help="add only, don't clear")
    parser.add_argument("--limit", type=int, default=20, help="VODs per channel (default 20)")
    add_env_arg(parser)
    return parser


def run(args: argparse.Namespace) -> int:
    load_env(getattr(args, "env", None) or "prod")
    asyncio.run(
        backfill_sessions(
            keep_existing=bool(getattr(args, "keep_existing", False)),
            limit=int(getattr(args, "limit", 20) or 20),
        )
    )
    return 0


def _main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(_main())
