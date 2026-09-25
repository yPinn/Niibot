"""Encrypt or repair Twitch credentials in bounded DB batches.

Run after migration 100 and before the future version-one contract migration:

    python -m scripts.twitch_ops.credentials --dry-run
    python -m scripts.twitch_ops.credentials --batch-size 100

Repair rows whose version was retained while a legacy writer stored plaintext:

    python -m scripts.twitch_ops.credentials --repair-missing-envelopes --dry-run
    python -m scripts.twitch_ops.credentials --repair-missing-envelopes --batch-size 100
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncpg

from scripts._lib import add_env_arg, load_env, require_db_context
from shared.twitch_token_backfill import (
    backfill_twitch_token_batch,
    repair_twitch_token_envelope_batch,
)
from shared.twitch_token_crypto import encrypt_twitch_token


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_env_arg(parser)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--repair-missing-envelopes",
        action="store_true",
        help="repair version-one rows written without the required v1 envelope",
    )
    return parser.parse_args()


async def _run(*, batch_size: int, dry_run: bool, repair_missing_envelopes: bool) -> None:
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
        if repair_missing_envelopes:
            count_sql = (
                "SELECT COUNT(*) FROM tokens WHERE encryption_version = 1 "
                "AND (token NOT LIKE 'v1:%' OR refresh NOT LIKE 'v1:%')"
            )
            operation = repair_twitch_token_envelope_batch
            label = "Missing-envelope Twitch credential rows"
        else:
            count_sql = "SELECT COUNT(*) FROM tokens WHERE encryption_version = 0"
            operation = backfill_twitch_token_batch
            label = "Legacy Twitch credential rows"

        remaining = await conn.fetchval(count_sql)
        if dry_run:
            print(f"{label}: {remaining}")
            return

        total = 0
        while True:
            async with conn.transaction():
                updated = await operation(conn, key=key, batch_size=batch_size)
            total += updated
            if updated == 0:
                break
            print(f"Encrypted rows: {total}")

        remaining = await conn.fetchval(count_sql)
        print(f"Credential migration complete: updated={total}, remaining={remaining}")
    finally:
        await conn.close()


def run(args: argparse.Namespace) -> int:
    load_env(args.env)
    require_db_context(args.env)
    asyncio.run(
        _run(
            batch_size=args.batch_size,
            dry_run=args.dry_run,
            repair_missing_envelopes=args.repair_missing_envelopes,
        )
    )
    return 0


def main() -> None:
    run(_parse_args())


if __name__ == "__main__":
    main()
