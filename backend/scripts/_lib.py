"""Shared helpers for backend/scripts/* — env loading, DB, arg-parsing, IO.

Every script under backend/scripts/ (and the `nb` dispatcher) uses these so the
env-file load order, staging selection, DB connection, and confirmation prompts
stay identical everywhere.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

# service name -> env file directory relative to BACKEND_DIR
_SERVICE_DIRS = {"api", "twitch", "discord", "scrapling"}


def backend_dir() -> Path:
    return BACKEND_DIR


def ensure_backend_on_path() -> None:
    """Put backend/ on sys.path so `shared.*` / `api.*` / `twitch.*` resolve."""
    p = str(BACKEND_DIR)
    if p not in sys.path:
        sys.path.insert(0, p)


def utf8_stdio() -> None:
    """Force UTF-8 stdout/stderr so Unicode symbols print on Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


# ── env ──────────────────────────────────────────────────────────────────────


def add_env_arg(parser: argparse.ArgumentParser) -> None:
    """Add a `--env {prod,staging}` option (default prod)."""
    parser.add_argument(
        "--env",
        choices=("prod", "staging"),
        default="prod",
        help="Which env file set to load (default: prod)",
    )


def load_env(env: str = "prod", *, service: str | None = None) -> None:
    """Load env files into os.environ, mirroring docker-compose / twitch_oauth order.

    prod:     shared.env  ->  shared.env.local (override)  ->  <service>/.env (override)
    staging:  shared.staging.env  ->  shared.staging.env.local  ->  <service>/.env.staging

    `shared.*.local` and the service file are optional. Names match
    scripts/env.sh's STAGING_FILES logic. pydantic `get_settings()` also picks
    these up because env vars beat its `env_file`.
    """
    if env not in ("prod", "staging"):
        raise ValueError(f"env must be 'prod' or 'staging', got {env!r}")

    suffix = "" if env == "prod" else ".staging"
    shared = BACKEND_DIR / f"shared{suffix}.env"
    shared_local = BACKEND_DIR / f"shared{suffix}.env.local"

    if not shared.exists():
        raise FileNotFoundError(
            f"{shared} not found — run `npm run nb -- env init` (or bash scripts/env.sh init)"
        )

    load_dotenv(shared, encoding="utf-8")
    if shared_local.exists():
        load_dotenv(shared_local, encoding="utf-8", override=True)

    if service:
        if service not in _SERVICE_DIRS:
            raise ValueError(
                f"unknown service {service!r}; expected one of {sorted(_SERVICE_DIRS)}"
            )
        svc = BACKEND_DIR / service / (".env" if env == "prod" else ".env.staging")
        if svc.exists():
            load_dotenv(svc, encoding="utf-8", override=True)


def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("[ERROR] DATABASE_URL not set — did you call load_env() first?")
    return url


# ── db ───────────────────────────────────────────────────────────────────────


@contextlib.asynccontextmanager
async def db_conn(
    env: str = "prod", *, service: str | None = None
) -> AsyncIterator[asyncpg.Connection]:
    """Yield a single asyncpg connection; loads env first, closes on exit."""
    load_env(env, service=service)
    conn = await asyncpg.connect(database_url(), statement_cache_size=0)
    try:
        yield conn
    finally:
        await conn.close()


@contextlib.asynccontextmanager
async def db_pool(
    env: str = "prod", *, service: str | None = None, max_size: int = 4
) -> AsyncIterator[asyncpg.Pool]:
    """Yield an asyncpg pool; loads env first, closes on exit."""
    load_env(env, service=service)
    pool = await asyncpg.create_pool(
        database_url(), min_size=1, max_size=max_size, statement_cache_size=0
    )
    assert pool is not None
    try:
        yield pool
    finally:
        await pool.close()


# ── prompts ──────────────────────────────────────────────────────────────────


def confirm(prompt: str, assume_yes: bool = False) -> bool:
    """Confirm a destructive action. Refuses (False) in a non-interactive shell."""
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        print(f"[ERROR] {prompt} Refusing without --yes in a non-interactive shell.")
        return False
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
