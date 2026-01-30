"""Run database migrations"""

import asyncio
import sys
from pathlib import Path

import asyncpg

# Add parent directory to path to import config
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.core.config import get_settings


async def run_migration(migration_file: str):
    """Run a specific migration file"""
    settings = get_settings()
    # Set statement_cache_size=0 for pgbouncer compatibility
    conn = await asyncpg.connect(settings.database_url, statement_cache_size=0)

    try:
        migration_path = (
            Path(__file__).parent.parent / "twitch" / "database" / "migrations" / migration_file
        )

        if not migration_path.exists():
            print(f"Error: Migration file not found: {migration_path}")
            return False

        print(f"Running migration: {migration_file}")

        with open(migration_path, encoding="utf-8") as f:
            migration_sql = f.read()

        await conn.execute(migration_sql)
        print(f"✓ Migration completed successfully: {migration_file}")
        return True

    except Exception as e:
        print(f"✗ Migration failed: {e}")
        return False

    finally:
        await conn.close()


async def run_all_migrations():
    """Run all migrations in order"""
    migrations_dir = Path(__file__).parent.parent / "twitch" / "database" / "migrations"
    migration_files = sorted([f.name for f in migrations_dir.glob("*.sql")])

    if not migration_files:
        print("No migration files found.")
        return

    print(f"Found {len(migration_files)} migration(s) to run:\n")

    success_count = 0
    for migration_file in migration_files:
        if await run_migration(migration_file):
            success_count += 1
        print()

    print(f"Completed: {success_count}/{len(migration_files)} migrations successful")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Run specific migration
        migration_file = sys.argv[1]
        asyncio.run(run_migration(migration_file))
    else:
        # Run all migrations
        asyncio.run(run_all_migrations())
