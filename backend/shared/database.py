"""Unified database connection management for all Niibot services.

Connection modes (auto-detected from DATABASE_URL port):
  - Session mode  (port 5432) : persistent connections, supports prepared statements
  - Transaction mode (port 6543) : external connection pooler (PgBouncer/Pgpool-II), no prepared statements
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import os
import socket
import ssl as _ssl
from collections.abc import AsyncGenerator
from dataclasses import dataclass, fields
from typing import Any, ClassVar
from urllib.parse import parse_qs, urlparse

import asyncpg

LOGGER: logging.Logger = logging.getLogger(__name__)

# Hosts for which an unencrypted DB connection is acceptable (local dev / the
# private Docker network).  Any other host is assumed to be a managed/remote
# Postgres reachable over a network we don't control, so TLS is required.
_LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres", "db", "nb-pg"}
_VALID_SSL_MODES = {
    "disable",
    "allow",
    "prefer",
    "require",
    "verify-ca",
    "verify-full",
}


def resolve_db_ssl(database_url: str) -> str | None:
    """Return the ``ssl`` argument for ``asyncpg.create_pool``.

    Priority:
      1. ``DB_SSL`` env var (disable|allow|prefer|require|verify-ca|verify-full)
      2. an ``sslmode`` already present in the DSN query → ``None`` (let asyncpg
         honour the DSN rather than silently overriding it)
      3. a local / container-local host → ``"prefer"`` (plaintext is fine on a
         trusted network and keeps local dev zero-config)
      4. anything else (remote / managed Postgres) → ``"require"`` so the
         connection is always encrypted
    """
    env_mode = os.getenv("DB_SSL", "").strip().lower()
    if env_mode in _VALID_SSL_MODES:
        return env_mode
    if env_mode:
        LOGGER.warning("Ignoring invalid DB_SSL=%r; falling back to auto-detection", env_mode)

    parsed = urlparse(database_url)
    if "sslmode" in parse_qs(parsed.query):
        return None

    host = (parsed.hostname or "").lower()
    return "prefer" if host in _LOCAL_DB_HOSTS else "require"


@dataclass
class PoolConfig:
    """Database pool configuration with sensible defaults."""

    min_size: int = 1
    max_size: int = 5
    timeout: float = 10.0
    command_timeout: float = 15.0
    max_inactive_connection_lifetime: float = 600.0
    max_retries: int = 3
    retry_delay: float = 3.0

    # Per-service preset overrides
    # All services use session mode (5432) with min_size=1 and heartbeat
    # loops to detect dead connections and reconnect automatically.
    # Transaction mode (6543) is only needed for external poolers (PgBouncer).
    _SERVICE_PRESETS: ClassVar[dict[str, dict]] = {
        "api": {"min_size": 1, "max_size": 3},
        "discord": {"min_size": 1, "max_size": 2},
        "twitch": {"min_size": 1, "max_size": 5},
    }

    @classmethod
    def for_service(cls, service: str, **overrides) -> PoolConfig:
        """Create a PoolConfig with service-specific presets.

        Shared defaults (timeout, keepalive, etc.) come from the dataclass
        defaults. Only pool sizing / retry differ per service.
        """
        valid_keys = {f.name for f in fields(cls) if not f.name.startswith("_")}
        preset = dict(cls._SERVICE_PRESETS.get(service, {}))
        preset.update(overrides)
        filtered = {k: v for k, v in preset.items() if k in valid_keys}
        return cls(**filtered)


class DatabaseManager:
    """Manages PostgreSQL connection pool lifecycle.

    Unified manager used by API, Twitch, and Discord services.
    Handles connection retry logic and proper lifecycle management.
    """

    def __init__(self, database_url: str, config: PoolConfig | None = None):
        self.database_url = database_url
        self.config = config or PoolConfig()
        self._pool: asyncpg.Pool | None = None
        self._pooler_mode: str = "transaction" if ":6543" in database_url else "session"

    # ── Pool builders (separate code paths, no if/else) ──────────────

    @staticmethod
    async def _register_json_codecs(conn: asyncpg.Connection) -> None:
        """Register JSON/JSONB codecs so asyncpg returns dicts instead of raw strings."""
        for typ in ("jsonb", "json"):
            await conn.set_type_codec(
                typ, encoder=_json.dumps, decoder=_json.loads, schema="pg_catalog"
            )

    async def _init_session_connection(self, conn: asyncpg.Connection) -> None:
        """Initialize new connections for Session Pooler.

        Sets session-level statement timeout and registers JSON/JSONB codecs.
        """
        timeout_ms = int(self.config.command_timeout * 1000)
        await conn.execute(f"SET statement_timeout = {timeout_ms}")
        await self._register_json_codecs(conn)

    def _session_pool_kwargs(self) -> dict[str, Any]:
        """Build asyncpg.create_pool kwargs for session mode (port 5432).

        - Prepared statements enabled (cache=100)
        - Session-level init (SET statement_timeout)
        - Maintains min_size idle connections
        - ssl: required for remote hosts, "prefer" for local (see resolve_db_ssl)
        """
        cfg = self.config
        kwargs: dict[str, Any] = {
            "dsn": self.database_url,
            "min_size": cfg.min_size,
            "max_size": cfg.max_size,
            "timeout": cfg.timeout,
            "command_timeout": cfg.command_timeout,
            "statement_cache_size": 100,
            "max_inactive_connection_lifetime": cfg.max_inactive_connection_lifetime,
            "init": self._init_session_connection,
        }
        ssl_arg = resolve_db_ssl(self.database_url)
        if ssl_arg is not None:
            kwargs["ssl"] = ssl_arg
        return kwargs

    def _transaction_pool_kwargs(self) -> dict[str, Any]:
        """Build asyncpg.create_pool kwargs for transaction mode (port 6543).

        PgBouncer/external pooler in transaction mode:
        - No prepared statements (cache=0)
        - JSON codecs registered via init (client-side, persists per connection object)
        - SET commands not used (don't persist across transactions in pooler mode)
        - min_size=0: don't hold idle connections (pooler manages them)
        - max_inactive=0: release connections immediately after use
        - ssl: required for remote hosts, "prefer" for local (see resolve_db_ssl)
        """
        cfg = self.config
        kwargs: dict[str, Any] = {
            "dsn": self.database_url,
            "min_size": 0,
            "max_size": cfg.max_size,
            "timeout": cfg.timeout,
            "command_timeout": cfg.command_timeout,
            "statement_cache_size": 0,
            "max_inactive_connection_lifetime": 0,
            "init": self._register_json_codecs,
        }
        ssl_arg = resolve_db_ssl(self.database_url)
        if ssl_arg is not None:
            kwargs["ssl"] = ssl_arg
        return kwargs

    # ── Diagnostics ──────────────────────────────────────────────────

    def _diagnose_connection(self) -> None:
        """Log network-level diagnostics when DB connection fails."""
        parsed = urlparse(self.database_url)
        host = parsed.hostname or "unknown"
        port = parsed.port or 5432
        user = parsed.username or "unknown"

        LOGGER.info("[DB Diag] host=%s, port=%s, user=%s", host, port, user)

        # 1. DNS resolution
        try:
            addrs = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
            families = {a[0].name for a in addrs}
            ips = {a[4][0] for a in addrs}
            LOGGER.info("[DB Diag] DNS OK: %s (families: %s)", ips, families)
        except socket.gaierror as e:
            LOGGER.error("[DB Diag] DNS FAILED: %s", e)
            return

        # 2. Raw TCP connection
        for addr in addrs[:2]:
            family, _, _, _, sockaddr = addr
            try:
                sock = socket.socket(family, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect(sockaddr)
                ip, port_ = str(sockaddr[0]), str(sockaddr[1])
                LOGGER.info("[DB Diag] TCP OK: %s:%s (%s)", ip, port_, family.name)
                # 3. SSL handshake
                try:
                    ctx = _ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = _ssl.CERT_NONE
                    ssock = ctx.wrap_socket(sock, server_hostname=host)
                    LOGGER.info("[DB Diag] SSL OK: %s", ssock.version())
                    ssock.close()
                except Exception as e:
                    LOGGER.error("[DB Diag] SSL FAILED: %s: %s", type(e).__name__, e)
                    sock.close()
            except Exception as e:
                LOGGER.error(
                    "[DB Diag] TCP FAILED to %s:%s: %s: %s",
                    sockaddr[0],
                    sockaddr[1],
                    type(e).__name__,
                    e,
                )

    # ── Lifecycle ────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Initialize database connection pool with retry."""
        if self._pool is not None:
            LOGGER.warning("Database pool already initialized")
            return

        # Select pool builder for detected pooler mode
        _builders = {
            "session": self._session_pool_kwargs,
            "transaction": self._transaction_pool_kwargs,
        }
        pool_kwargs = _builders[self._pooler_mode]()
        LOGGER.info("Connecting with %s pooler mode", self._pooler_mode)

        cfg = self.config
        for attempt in range(1, cfg.max_retries + 1):
            pool: asyncpg.Pool | None = None
            try:
                pool = await asyncpg.create_pool(**pool_kwargs)

                # Verify pool is usable before exposing it
                async with pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")

                # Only assign after verification passes — prevents race
                # where requests see a pool that gets closed during retry.
                self._pool = pool

                effective_min = pool_kwargs.get("min_size", 0)
                effective_cache = pool_kwargs.get("statement_cache_size", 0)
                LOGGER.info(
                    "Database pool created and verified (mode=%s, size=%d-%d, cache=%d)",
                    self._pooler_mode,
                    effective_min,
                    cfg.max_size,
                    effective_cache,
                )
                return
            except Exception as e:
                if pool:
                    try:
                        await pool.close()
                    except Exception:
                        pass
                if attempt < cfg.max_retries:
                    delay = cfg.retry_delay * (2 ** (attempt - 1))
                    LOGGER.warning(
                        "Database connection attempt %d/%d failed: %s: %s, retrying in %.1fs...",
                        attempt,
                        cfg.max_retries,
                        type(e).__name__,
                        e or repr(e),
                        delay,
                    )
                    # Run diagnostics on first failure
                    if attempt == 1:
                        try:
                            self._diagnose_connection()
                        except Exception:
                            pass
                    await asyncio.sleep(delay)
                else:
                    LOGGER.exception(
                        "Database connection failed after %d attempts", cfg.max_retries
                    )
                    raise

    async def reconnect(self) -> None:
        """Destroy a dead pool and create a fresh one.

        Called by heartbeat loops when consecutive health checks fail,
        indicating the pool's connections are stale or the database
        was temporarily unavailable.
        """
        old = self._pool
        self._pool = None  # clear first so connect() won't short-circuit

        if old is not None:
            try:
                await asyncio.wait_for(old.close(), timeout=5.0)
            except Exception:
                # close() hung or errored — force-kill remaining connections
                try:
                    old.terminate()
                except Exception:
                    pass

        LOGGER.info("Reconnecting database pool...")
        await self.connect()  # raises on final failure (after retries)

    async def disconnect(self) -> None:
        """Close database connection pool."""
        if self._pool is None:
            return

        try:
            await self._pool.close()
            self._pool = None
            LOGGER.info("Database pool closed")
        except Exception:
            LOGGER.exception("Error closing database pool")

    async def check_health(self) -> bool:
        """Test if pool can actually execute a query."""
        if self._pool is None:
            return False
        try:
            async with self._pool.acquire(timeout=2.0) as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

    @property
    def is_connected(self) -> bool:
        """Return True if the pool has been initialized and is ready."""
        return self._pool is not None

    def pool_stats(self) -> dict[str, int] | None:
        """Return pool size/idle/min/max, or None if not connected."""
        if self._pool is None:
            return None
        return {
            "size": self._pool.get_size(),
            "idle": self._pool.get_idle_size(),
            "min_size": self._pool.get_min_size(),
            "max_size": self._pool.get_max_size(),
        }

    @property
    def pool(self) -> asyncpg.Pool:
        """Get the database connection pool. Raises if not initialized."""
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        return self._pool

    async def get_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Yield a connection from the pool (for dependency injection)."""
        async with self.pool.acquire() as conn:
            yield conn


async def pool_heartbeat_loop(db_manager: DatabaseManager) -> None:
    """Shared pool heartbeat for all services.

    Periodically pings the DB pool to detect and recover dead connections.
    After 3 consecutive failures triggers ``db_manager.reconnect()``.
    Callers should wrap this in ``asyncio.create_task`` and cancel on shutdown.
    """
    interval = 60
    fail_count = 0
    while True:
        await asyncio.sleep(interval)
        try:
            if not db_manager.is_connected:
                raise RuntimeError("Pool is None")
            async with db_manager.pool.acquire(timeout=10.0) as conn:
                await conn.fetchval("SELECT 1")
            if fail_count > 0:
                LOGGER.info("Pool heartbeat recovered after %d failures", fail_count)
            fail_count = 0
            interval = 60
        except asyncio.CancelledError:
            break
        except Exception as e:
            fail_count += 1
            if fail_count <= 3:
                LOGGER.warning(
                    "Pool heartbeat failed (%d): %s: %s", fail_count, type(e).__name__, e
                )

            if fail_count == 3:
                LOGGER.warning("Pool appears dead, attempting reconnect...")
                try:
                    await db_manager.reconnect()
                    LOGGER.info("Pool reconnected successfully")
                    fail_count = 0
                    interval = 60
                    continue
                except Exception as re_err:
                    LOGGER.error("Pool reconnect failed: %s: %s", type(re_err).__name__, re_err)
                    fail_count = 0
                    interval = 120
                    continue

            interval = min(60 * (2 ** min(fail_count - 1, 1)), 120)
