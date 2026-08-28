"""Run database migrations using shared.migrations.runner.

    npm run nb -- db migrate [--dry] [--env staging]
    uv run --directory backend python scripts/db_migrate.py [--dry] [--env staging]

--dry lists pending migrations without applying them.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from _lib import add_env_arg, db_pool, ensure_backend_on_path

ensure_backend_on_path()

from shared.migrations.runner import MigrationRunner  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

_VERSIONS_DIR = Path(__file__).resolve().parent.parent / "shared" / "migrations" / "versions"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run database migrations.")
    parser.add_argument("--dry", action="store_true", help="show pending migrations, don't apply")
    add_env_arg(parser)
    return parser


async def _run(args: argparse.Namespace) -> int:
    async with db_pool(args.env, max_size=2) as pool:
        runner = MigrationRunner(pool)
        await runner.apply_version_renames()

        if args.dry:
            applied = await runner.get_applied()
            pending = [f.stem for f in sorted(_VERSIONS_DIR.glob("*.sql")) if f.stem not in applied]
            print(f"Applied: {len(applied)} | Pending: {len(pending)}")
            for v in pending:
                print(f"  -> {v}")
            if not pending:
                print("Database is up to date.")
            return 0

        newly_applied = await runner.run_pending()
        print(
            f"Applied {len(newly_applied)} migration(s)."
            if newly_applied
            else "No pending migrations."
        )
        return 0


def run(args: argparse.Namespace) -> int:
    return asyncio.run(_run(args))


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
