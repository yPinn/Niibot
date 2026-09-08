"""Backfill deterministic collection draws for historical successful check-ins.

Examples (report-only is the default):

    uv run --directory backend python scripts/backfill_checkin_collections.py
    uv run --directory backend python scripts/backfill_checkin_collections.py --env staging --apply
    uv run --directory backend python scripts/backfill_checkin_collections.py --apply --yes

Every write requires both ``--apply`` and an explicit confirmation. The script
never creates historical Live Display events.
"""

from __future__ import annotations

import argparse
import asyncio

from _lib import add_env_arg, confirm, db_conn, ensure_backend_on_path, utf8_stdio

ensure_backend_on_path()
utf8_stdio()

from shared.collection_backfill import (  # noqa: E402
    DEFAULT_BATCH_SIZE,
    MAX_BATCH_SIZE,
    BackfillReport,
    backfill_checkin_collections,
)


def _batch_size(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("batch size must be an integer") from exc
    if not 1 <= parsed <= MAX_BATCH_SIZE:
        raise argparse.ArgumentTypeError(f"batch size must be between 1 and {MAX_BATCH_SIZE}")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--batch-size",
        type=_batch_size,
        default=DEFAULT_BATCH_SIZE,
        help=f"maximum check-ins per viewer transaction (default {DEFAULT_BATCH_SIZE})",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report candidates without writes")
    mode.add_argument("--apply", action="store_true", help="write missing historical draws")
    parser.add_argument("-y", "--yes", action="store_true", help="confirm apply without prompting")
    add_env_arg(parser)
    return parser


def is_dry_run(args: argparse.Namespace) -> bool:
    """No flag and ``--dry-run`` are both safe report-only operation."""
    return not bool(args.apply)


def _print_report(report: BackfillReport, *, dry_run: bool) -> None:
    mode = "dry-run" if dry_run else "apply"
    print(f"Collection check-in backfill: mode={mode}")
    print(
        f"scanned={report.scanned} inserted={report.inserted} skipped={report.skipped} "
        f"remaining={report.remaining} failures={report.failures}"
    )


async def _run(args: argparse.Namespace) -> int:
    dry_run = is_dry_run(args)
    if not dry_run and not confirm(
        "Apply historical collection draws to the configured database?",
        assume_yes=args.yes,
    ):
        print("[REFUSED] Collection backfill was not applied.")
        return 2

    async with db_conn(args.env) as conn:
        report = await backfill_checkin_collections(
            conn,
            batch_size=args.batch_size,
            dry_run=dry_run,
        )
    _print_report(report, dry_run=dry_run)
    if not dry_run and (report.failures > 0 or report.remaining > 0):
        return 1
    return 0


def run(args: argparse.Namespace) -> int:
    return asyncio.run(_run(args))


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
