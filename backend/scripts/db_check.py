"""Check database setup for new token NOTIFY trigger.

Verifies:
1. Triggers exist (channel_toggle, new_token)
2. Functions exist (fn_notify_channel_toggle, fn_notify_new_token)
3. Table structures (tokens, channels)
4. Simulates new user flow
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "api" / ".env")


async def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set")
        sys.exit(1)

    conn = await asyncpg.connect(database_url, statement_cache_size=0)

    try:
        print("=" * 60)
        print("DATABASE SETUP CHECK")
        print("=" * 60)

        # 1. Check triggers
        print("\n[1] TRIGGERS on tokens table:")
        triggers = await conn.fetch("""
            SELECT trigger_name, event_manipulation, action_timing
            FROM information_schema.triggers
            WHERE event_object_table = 'tokens'
        """)
        if triggers:
            for t in triggers:
                print(
                    f"    [OK] {t['trigger_name']} ({t['action_timing']} {t['event_manipulation']})"
                )
        else:
            print("    [MISSING] No triggers found on tokens table!")

        print("\n[2] TRIGGERS on channels table:")
        triggers = await conn.fetch("""
            SELECT trigger_name, event_manipulation, action_timing
            FROM information_schema.triggers
            WHERE event_object_table = 'channels'
        """)
        if triggers:
            for t in triggers:
                print(
                    f"    [OK] {t['trigger_name']} ({t['action_timing']} {t['event_manipulation']})"
                )
        else:
            print("    [MISSING] No triggers found!")

        # 2. Check functions
        print("\n[3] NOTIFY FUNCTIONS:")
        functions = await conn.fetch("""
            SELECT routine_name
            FROM information_schema.routines
            WHERE routine_name LIKE 'fn_notify%'
            AND routine_type = 'FUNCTION'
        """)
        if functions:
            for f in functions:
                print(f"    [OK] {f['routine_name']}")
        else:
            print("    [MISSING] No notify functions found!")

        # 3. Check table structures
        print("\n[4] TOKENS TABLE COLUMNS:")
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'tokens'
            ORDER BY ordinal_position
        """)
        for c in columns:
            print(f"    - {c['column_name']}: {c['data_type']} (nullable: {c['is_nullable']})")

        print("\n[5] CHANNELS TABLE COLUMNS:")
        columns = await conn.fetch("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'channels'
            ORDER BY ordinal_position
        """)
        for c in columns:
            print(f"    - {c['column_name']}: {c['data_type']} (nullable: {c['is_nullable']})")

        # 4. Check existing data
        print("\n[6] CURRENT DATA:")
        token_count = await conn.fetchval("SELECT COUNT(*) FROM tokens")
        channel_count = await conn.fetchval("SELECT COUNT(*) FROM channels")
        enabled_count = await conn.fetchval("SELECT COUNT(*) FROM channels WHERE enabled = TRUE")
        print(f"    - Tokens: {token_count}")
        print(f"    - Channels: {channel_count} (enabled: {enabled_count})")

        # 5. Check applied migrations
        print("\n[7] APPLIED MIGRATIONS:")
        migrations = await conn.fetch("""
            SELECT version, applied_at
            FROM schema_migrations
            ORDER BY applied_at
        """)
        for m in migrations:
            print(f"    [OK] {m['version']} (applied: {m['applied_at']})")

        # 6. Test NOTIFY (simulation)
        print("\n[8] NOTIFY SIMULATION TEST:")
        print("    Testing pg_notify('new_token', ...)...")
        await conn.execute("""
            SELECT pg_notify('new_token', '{"user_id": "test_simulation_only"}')
        """)
        print("    [OK] pg_notify executed successfully (no error)")

        print("\n" + "=" * 60)
        print("CHECK COMPLETE")
        print("=" * 60)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
