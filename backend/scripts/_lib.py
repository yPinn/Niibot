"""Shared helpers for backend/scripts/* — env loading, DB, arg-parsing, IO.

`nb` and every standalone script use these so the env-file load order, staging
selection, DB connection and confirmation prompts stay identical everywhere.
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

_SERVICE_DIRS = {"api", "twitch", "discord", "scrapling"}


def ensure_backend_on_path() -> None:
    """Put backend/ on sys.path so `shared.*` / `api.*` / `twitch.*` resolve."""
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))


def utf8_stdio() -> None:
    """Force UTF-8 stdout/stderr so Unicode symbols print on Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]


# ── env ──────────────────────────────────────────────────────────────────────


def add_env_arg(parser: argparse.ArgumentParser) -> None:
    """Add `--env {prod,staging}` (default prod)."""
    parser.add_argument(
        "--env", choices=("prod", "staging"), default="prod", help="env file set (default: prod)"
    )


def load_env(env: str = "prod", *, service: str | None = None) -> None:
    """Load env files into os.environ (env vars beat pydantic's env_file).

    Order — later overrides earlier:
        shared[.staging].env  ->  shared[.staging].env.local  ->  <service>/.env[.staging]

    The `.local` and service files are optional; naming matches scripts/env.sh.
    """
    if env not in ("prod", "staging"):
        raise ValueError(f"env must be 'prod' or 'staging', got {env!r}")

    suffix = "" if env == "prod" else ".staging"
    shared = BACKEND_DIR / f"shared{suffix}.env"
    if not shared.exists():
        raise FileNotFoundError(f"{shared} not found — run `npm run nb -- env init`")

    load_dotenv(shared, encoding="utf-8")
    shared_local = BACKEND_DIR / f"shared{suffix}.env.local"
    if shared_local.exists():
        load_dotenv(shared_local, encoding="utf-8", override=True)

    if service:
        if service not in _SERVICE_DIRS:
            raise ValueError(f"unknown service {service!r}; expected {sorted(_SERVICE_DIRS)}")
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
async def db_conn(env: str = "prod") -> AsyncIterator[asyncpg.Connection]:
    """Yield a single asyncpg connection; loads env first, closes on exit."""
    load_env(env)
    conn = await asyncpg.connect(database_url(), statement_cache_size=0)
    try:
        yield conn
    finally:
        await conn.close()


@contextlib.asynccontextmanager
async def db_pool(env: str = "prod", *, max_size: int = 4) -> AsyncIterator[asyncpg.Pool]:
    """Yield an asyncpg pool; loads env first, closes on exit."""
    load_env(env)
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
    """Confirm a destructive action; False without an explicit yes."""
    if assume_yes:
        return True
    try:
        return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        print(f"[ERROR] {prompt} Refusing — no input (pass --yes to skip).")
        return False
