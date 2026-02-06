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
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import asyncpg
import httpx

# Ensure backend/ is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.core.config import get_settings


def parse_duration(duration_str: str) -> float:
    """Parse Twitch duration string (e.g., '3h2m1s') to hours."""
    hours = 0
    minutes = 0
    seconds = 0

    h_match = re.search(r"(\d+)h", duration_str)
    m_match = re.search(r"(\d+)m", duration_str)
    s_match = re.search(r"(\d+)s", duration_str)

    if h_match:
        hours = int(h_match.group(1))
    if m_match:
        minutes = int(m_match.group(1))
    if s_match:
        seconds = int(s_match.group(1))

    return hours + minutes / 60 + seconds / 3600


async def get_app_access_token(client_id: str, client_secret: str) -> str | None:
    """Get Twitch app access token."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
        )
        if response.status_code != 200:
            print(f"[X] Failed to get app token: {response.status_code}")
            return None
        return response.json().get("access_token")


async def fetch_videos(client_id: str, app_token: str, user_id: str, limit: int = 20) -> list[dict]:
    """Fetch VODs for a user from Twitch API."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.twitch.tv/helix/videos",
            params={
                "user_id": user_id,
                "type": "archive",
                "first": min(limit, 100),
            },
            headers={
                "Authorization": f"Bearer {app_token}",
                "Client-Id": client_id,
            },
        )
        if response.status_code != 200:
            print(f"  [X] Failed to fetch videos: {response.status_code}")
            return []
        return response.json().get("data", [])


async def fetch_game_by_name(client_id: str, app_token: str, game_name: str) -> dict | None:
    """Fetch game info by name to get game_id."""
    if not game_name:
        return None

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.twitch.tv/helix/games",
            params={"name": game_name},
            headers={
                "Authorization": f"Bearer {app_token}",
                "Client-Id": client_id,
            },
        )
        if response.status_code != 200:
            return None
        data = response.json().get("data", [])
        return data[0] if data else None


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

    # Connect to database
    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0)

    try:
        # Get Twitch credentials
        client_id = settings.client_id
        client_secret = settings.client_secret

        if not client_id or not client_secret:
            print("[X] Missing CLIENT_ID or CLIENT_SECRET in settings")
            return

        # Get app token
        print("\n[0/3] Authenticating with Twitch API...")
        app_token = await get_app_access_token(client_id, client_secret)
        if not app_token:
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
        _game_cache: dict[str, str | None] = {}  # game_name -> game_id

        for channel in channels:
            channel_id = channel["channel_id"]
            channel_name = channel["channel_name"]
            print(f"\n  > Channel: {channel_name} ({channel_id})")

            videos = await fetch_videos(client_id, app_token, channel_id, limit)
            if not videos:
                print("    No VODs found (channel may not have VODs enabled)")
                continue

            print(f"    Found {len(videos)} VODs")

            for video in videos:
                # Parse video data
                title = video.get("title", "Untitled")
                created_at_str = video.get("created_at")
                duration_str = video.get("duration", "0s")

                if not created_at_str:
                    continue

                # Parse timestamps
                started_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                duration_hours = parse_duration(duration_str)
                ended_at = started_at + timedelta(hours=duration_hours)

                # Get game info (VODs don't include game_id directly, need to look it up)
                # Note: VODs may have multiple games played, we just use None for now
                game_name = None
                game_id = None

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
                    game_name,
                    game_id,
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
        await conn.close()


if __name__ == "__main__":
    # Parse command line arguments
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
