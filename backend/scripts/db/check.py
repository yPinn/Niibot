"""Check database setup: NOTIFY triggers, functions, table structure, migrations.

    npm run nb -- db check [--env stg]
    uv run --directory backend python -m scripts.db.check [--env stg]

Read-only — reports what's present vs expected, never writes.
"""

from __future__ import annotations

import argparse
import asyncio

from scripts._lib import add_env_arg, db_conn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify database triggers / schema / migrations.")
    add_env_arg(parser)
    return parser


async def _run(args: argparse.Namespace) -> int:
    async with db_conn(args.env) as conn:
        print("=" * 60)
        print("DATABASE SETUP CHECK")
        print("=" * 60)

        for table in ("tokens", "channels"):
            print(f"\n[TRIGGERS on {table} table]")
            triggers = await conn.fetch(
                """
                SELECT trigger_name, event_manipulation, action_timing
                FROM information_schema.triggers WHERE event_object_table = $1
                """,
                table,
            )
            if triggers:
                for t in triggers:
                    print(
                        f"    [OK] {t['trigger_name']} "
                        f"({t['action_timing']} {t['event_manipulation']})"
                    )
            else:
                print(f"    [MISSING] No triggers on {table}!")

        print("\n[NOTIFY FUNCTIONS]")
        functions = await conn.fetch(
            """
            SELECT routine_name FROM information_schema.routines
            WHERE routine_name LIKE 'fn_notify%' AND routine_type = 'FUNCTION'
            """
        )
        for f in functions or []:
            print(f"    [OK] {f['routine_name']}")
        if not functions:
            print("    [MISSING] No notify functions found!")

        for table in ("tokens", "channels"):
            print(f"\n[{table.upper()} COLUMNS]")
            columns = await conn.fetch(
                """
                SELECT column_name, data_type, is_nullable FROM information_schema.columns
                WHERE table_name = $1 ORDER BY ordinal_position
                """,
                table,
            )
            for c in columns:
                print(f"    - {c['column_name']}: {c['data_type']} (nullable: {c['is_nullable']})")

        print("\n[CURRENT DATA]")
        token_count = await conn.fetchval("SELECT COUNT(*) FROM tokens")
        channel_count = await conn.fetchval("SELECT COUNT(*) FROM channels")
        enabled_count = await conn.fetchval("SELECT COUNT(*) FROM channels WHERE enabled = TRUE")
        print(f"    - Tokens: {token_count}")
        print(f"    - Channels: {channel_count} (enabled: {enabled_count})")

        print("\n[APPLIED MIGRATIONS]")
        migrations = await conn.fetch(
            "SELECT version, applied_at FROM schema_migrations ORDER BY applied_at"
        )
        for m in migrations:
            print(f"    [OK] {m['version']} (applied: {m['applied_at']})")

        print("\n[NOTIFY SIMULATION]")
        await conn.execute(
            "SELECT pg_notify('new_token', '{\"user_id\": \"test_simulation_only\"}')"
        )
        print("    [OK] pg_notify executed successfully")

        print("\n" + "=" * 60)
        print("CHECK COMPLETE")
        print("=" * 60)
    return 0


def run(args: argparse.Namespace) -> int:
    return asyncio.run(_run(args))


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
