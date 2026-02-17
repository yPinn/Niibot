"""Backfill stream sessions from Twitch VODs (real historical data).

This script:
1. Clears existing test/fake session data
2. Fetches real VODs from Twitch API for each enabled channel
3. Creates session records from the VOD data

Usage:
    python db_backfill_sessions.py [--keep-existing] [--limit N]

Options:
    --keep-existing    Don't clear existing sessions, only add new ones
    --limit N          Limit VODs per channel (default: 20)
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

import asyncpg

# Ensure backend/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.core.config import get_settings
from api.services.twitch_api import TwitchAPIClient


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


if __name__ == "__main__":
    keep_existing = "--keep-existing" in sys.argv
    limit = 20

    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            try:
                limit = int(sys.argv[i + 1])
            except ValueError:
                print(f"Invalid limit value: {sys.argv[i + 1]}")
                sys.exit(1)

    asyncio.run(backfill_sessions(keep_existing=keep_existing, limit=limit))
