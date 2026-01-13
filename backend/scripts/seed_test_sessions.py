"""Generate test session data for development"""

import asyncio
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import asyncpg

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.core.config import get_settings


async def seed_test_sessions(channel_id: str = None):
    """Create test session data for the past 30 days"""

    # Get database URL from settings
    settings = get_settings()

    # Connect to database using DATABASE_URL
    # Set statement_cache_size=0 for pgbouncer compatibility
    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0)

    try:
        # Get channel_id if not provided
        if not channel_id:
            # Try to get the first channel from database
            row = await conn.fetchrow("SELECT channel_id FROM channels LIMIT 1")
            if row:
                channel_id = row["channel_id"]
                print(f"Using channel_id from database: {channel_id}")
            else:
                print("Error: No channels found in database. Please create a channel first.")
                return

        # Game data with IDs (box art URL is generated dynamically in frontend)
        games = [
            {"id": "509658", "name": "Just Chatting"},
            {"id": "21779", "name": "League of Legends"},
            {"id": "516575", "name": "VALORANT"},
            {"id": "27471", "name": "Minecraft"},
            {"id": "511224", "name": "Apex Legends"},
            {"id": "32982", "name": "Grand Theft Auto V"},
            {"id": "33214", "name": "Fortnite"},
            {"id": "32399", "name": "Counter-Strike"},
            {"id": "29595", "name": "Dota 2"},
            {"id": "488552", "name": "Overwatch 2"},
        ]

        # Stream titles
        titles = [
            "Chill stream with chat",
            "Learning new strategies",
            "Ranked grind!",
            "Viewer games!",
            "Road to Masters",
            "Community event",
            "Practice session",
            "Late night vibes",
            "Morning coffee stream",
            "Weekend marathon",
        ]

        # Generate 15-20 sessions over the past 30 days
        num_sessions = random.randint(15, 20)
        now = datetime.now()

        sessions = []
        for _ in range(num_sessions):
            # Random day in the past 30 days
            days_ago = random.randint(0, 29)
            # Random hour (more streams in evening)
            hour = random.choices(
                range(24),
                weights=[1, 1, 1, 1, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 10, 8, 6, 5, 4, 3, 2],
                k=1
            )[0]
            minute = random.randint(0, 59)

            started_at = now - timedelta(days=days_ago, hours=hour, minutes=minute)

            # Duration between 1-6 hours
            duration_hours = round(random.uniform(1.0, 6.0), 2)
            ended_at = started_at + timedelta(hours=duration_hours)

            # Random stats
            total_commands = random.randint(50, 500)
            new_follows = random.randint(0, 25)
            new_subs = random.randint(0, 10)
            raids_received = random.randint(0, 3)

            # Pick random game
            game = random.choice(games)

            session_data = {
                "channel_id": channel_id,
                "started_at": started_at,
                "ended_at": ended_at,
                "title": random.choice(titles),
                "game_id": game["id"],
                "game_name": game["name"],
                "duration_hours": duration_hours,
                "total_commands": total_commands,
                "new_follows": new_follows,
                "new_subs": new_subs,
                "raids_received": raids_received,
            }

            sessions.append(session_data)

        # Sort by started_at
        sessions.sort(key=lambda x: x["started_at"])

        # Insert sessions
        for session in sessions:
            result = await conn.fetchrow(
                """
                INSERT INTO stream_sessions
                    (channel_id, started_at, ended_at, title, game_id, game_name)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
                """,
                session["channel_id"],
                session["started_at"],
                session["ended_at"],
                session["title"],
                session["game_id"],
                session["game_name"],
            )

            session_id = result["id"]

            print(f"Created session {session_id}: {session['title']} - {session['game_name']}")
            print(f"  Started: {session['started_at']}")
            print(f"  Duration: {session['duration_hours']}h")
            print(f"  Game ID: {session['game_id']}")
            print(f"  Commands: {session['total_commands']}, Follows: {session['new_follows']}, Subs: {session['new_subs']}")
            print()

        print(f"\nSuccessfully created {len(sessions)} test sessions!")

    finally:
        await conn.close()


if __name__ == "__main__":
    # Allow passing channel_id as command line argument
    import sys
    channel_id = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(seed_test_sessions(channel_id))
