"""Encrypt legacy version-zero Twitch credentials in bounded DB batches.

Run after migration 100 and before the future version-one contract migration:

    python scripts/encrypt_twitch_tokens.py --dry-run
    python scripts/encrypt_twitch_tokens.py --batch-size 100
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

from shared.twitch_token_backfill import backfill_twitch_token_batch
from shared.twitch_token_crypto import encrypt_twitch_token

_BACKEND_DIR = Path(__file__).resolve().parent.parent


def _load_environment() -> None:
    load_dotenv(_BACKEND_DIR / "shared.env")
    load_dotenv(_BACKEND_DIR / "shared.env.local", override=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


async def _run(*, batch_size: int, dry_run: bool) -> None:
    database_url = os.getenv("DATABASE_URL", "")
    key = os.getenv("TWITCH_TOKEN_ENCRYPTION_KEY", "")
    if not database_url:
        raise SystemExit("DATABASE_URL is not configured")
    if not key:
        raise SystemExit("TWITCH_TOKEN_ENCRYPTION_KEY is not configured")
    if not 1 <= batch_size <= 1000:
        raise SystemExit("--batch-size must be between 1 and 1000")

    # Validate before opening a DB connection; never print the key.
    encrypt_twitch_token("validation", key)
    conn = await asyncpg.connect(database_url)
    try:
        remaining = await conn.fetchval("SELECT COUNT(*) FROM tokens WHERE encryption_version = 0")
        if dry_run:
            print(f"Legacy Twitch credential rows: {remaining}")
            return

        total = 0
        while True:
            async with conn.transaction():
                updated = await backfill_twitch_token_batch(conn, key=key, batch_size=batch_size)
            total += updated
            if updated == 0:
                break
            print(f"Encrypted rows: {total}")

        remaining = await conn.fetchval("SELECT COUNT(*) FROM tokens WHERE encryption_version = 0")
        print(f"Backfill complete: encrypted={total}, remaining={remaining}")
    finally:
        await conn.close()


def main() -> None:
    _load_environment()
    args = _parse_args()
    asyncio.run(_run(batch_size=args.batch_size, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
