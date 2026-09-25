"""Shared CLI helpers for env loading, database access, and prompts."""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from urllib.parse import urlparse

import asyncpg
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent

_SERVICE_DIRS = {"api", "twitch", "discord", "scrapling"}
ENV_CHOICES = ("dev", "stg", "prod")
_RUNTIME_NAMES = {"dev": "development", "stg": "staging", "prod": "production"}
_ENV_SELECTORS = {runtime: env for env, runtime in _RUNTIME_NAMES.items()}


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
    """Add the safe-by-default environment selector."""
    default = _ENV_SELECTORS.get(os.getenv("ENVIRONMENT", "").lower(), "dev")
    parser.add_argument(
        "--env",
        choices=ENV_CHOICES,
        default=default,
        help=f"environment file set (default: {default})",
    )


def _check_runtime_match(env: str) -> bool:
    """Return whether this is a container after validating its runtime label."""
    runtime = os.getenv("ENVIRONMENT", "").lower()
    selected = _ENV_SELECTORS.get(runtime)
    is_container = os.getenv("NIIBOT_RUNTIME_CONTEXT") == "container"
    if selected is not None and selected != env:
        raise SystemExit(f"selected environment {env!r} does not match runtime {runtime!r}")
    if is_container and selected is None:
        raise SystemExit(
            "container runtime ENVIRONMENT must be development, staging, or production"
        )
    return is_container


def load_env(env: str = "dev", *, service: str | None = None) -> None:
    """Load one explicit env set; injected container variables take precedence."""
    if env not in ENV_CHOICES:
        raise ValueError(f"env must be one of {ENV_CHOICES}, got {env!r}")
    if service is not None and service not in _SERVICE_DIRS:
        raise ValueError(f"unknown service {service!r}; expected {sorted(_SERVICE_DIRS)}")
    if _check_runtime_match(env):
        return

    shared = BACKEND_DIR / f"shared.{env}.env"
    if not shared.exists():
        if os.getenv("DATABASE_URL"):
            print(f"note: {shared.name} absent; using process environment", file=sys.stderr)
            return
        raise FileNotFoundError(f"{shared} not found — run `npm run nb -- env init {env}`")

    load_dotenv(shared, encoding="utf-8")
    if env == "dev":
        shared_local = BACKEND_DIR / "shared.dev.local.env"
        if shared_local.exists():
            load_dotenv(shared_local, encoding="utf-8", override=True)

    if service:
        svc = BACKEND_DIR / service / f".env.{env}"
        if svc.exists():
            load_dotenv(svc, encoding="utf-8", override=True)
        if env == "dev":
            svc_local = BACKEND_DIR / service / ".env.dev.local"
            if svc_local.exists():
                load_dotenv(svc_local, encoding="utf-8", override=True)


def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        sys.exit("[ERROR] DATABASE_URL not set — did you call load_env() first?")
    return url


def require_db_context(env: str) -> None:
    """Keep deployed databases reachable only from their Compose network."""
    if _check_runtime_match(env):
        return
    if env != "dev":
        raise SystemExit(
            f"{env} database commands must run in the matching container; "
            f"use `npm run nb -- stack {env} migrate` or `stack {env} exec`."
        )


def require_dev_database(url: str) -> None:
    """Refuse dev-only mutation tools unless the database is local."""
    is_container = _check_runtime_match("dev")
    host = (urlparse(url).hostname or "").lower()
    allowed = {"postgres"} if is_container else {"localhost", "127.0.0.1", "::1"}
    if host not in allowed:
        raise SystemExit(f"dev mutation requires a local dev database, got host {host!r}")


# ── db ───────────────────────────────────────────────────────────────────────


@contextlib.asynccontextmanager
async def db_conn(env: str = "dev") -> AsyncIterator[asyncpg.Connection]:
    """Yield a single asyncpg connection; loads env first, closes on exit."""
    load_env(env)
    require_db_context(env)
    conn = await asyncpg.connect(database_url(), statement_cache_size=0)
    try:
        yield conn
    finally:
        await conn.close()


@contextlib.asynccontextmanager
async def db_pool(env: str = "dev", *, max_size: int = 4) -> AsyncIterator[asyncpg.Pool]:
    """Yield an asyncpg pool; loads env first, closes on exit."""
    load_env(env)
    require_db_context(env)
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
