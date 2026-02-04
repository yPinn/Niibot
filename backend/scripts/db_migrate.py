"""Run database migrations using shared.migrations.runner.

Usage:
    python db_migrate.py          # Run all pending migrations
    python db_migrate.py --dry    # Show pending migrations without applying
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Ensure backend/ is on sys.path so shared.* is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncpg
from dotenv import load_dotenv

from shared.migrations.runner import MigrationRunner

# Try loading .env from api/ (has DATABASE_URL)
load_dotenv(Path(__file__).resolve().parent.parent / "api" / ".env")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


async def main() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set. Check api/.env or environment variables.")
        sys.exit(1)

    pool = await asyncpg.create_pool(database_url, min_size=1, max_size=2, statement_cache_size=0)
    if pool is None:
        print("ERROR: Failed to create connection pool.")
        sys.exit(1)

    try:
        runner = MigrationRunner(pool)

        if "--dry" in sys.argv:
            await runner.ensure_table()
            applied = await runner.get_applied()
            versions_dir = (
                Path(__file__).resolve().parent.parent / "shared" / "migrations" / "versions"
            )
            sql_files = sorted(versions_dir.glob("*.sql"))
            pending = [f.stem for f in sql_files if f.stem not in applied]

            print(f"Applied: {len(applied)} | Pending: {len(pending)}")
            for v in pending:
                print(f"  -> {v}")
            if not pending:
                print("Database is up to date.")
        else:
            newly_applied = await runner.run_pending()
            if not newly_applied:
                print("No pending migrations.")
            else:
                print(f"Applied {len(newly_applied)} migration(s).")
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
