"""Unified database connection management for all Niibot services.

Supabase connection modes:
  - Session Pooler  (port 5432) : persistent servers, supports prepared statements
  - Transaction Pooler (port 6543) : serverless/edge, no prepared statement support
"""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl as _ssl
from collections.abc import AsyncGenerator
from dataclasses import dataclass, fields
from typing import Any, ClassVar
from urllib.parse import urlparse

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class PoolConfig:
    """Database pool configuration with sensible defaults."""

    min_size: int = 1
    max_size: int = 5
    timeout: float = 5.0
    command_timeout: float = 15.0
    max_inactive_connection_lifetime: float = 30.0
    max_retries: int = 3
    retry_delay: float = 3.0

    # Keep-alive settings (Session Pooler only)
    tcp_keepalives_idle: int = 30
    tcp_keepalives_interval: int = 10
    tcp_keepalives_count: int = 3

    # Per-service preset overrides
    # - api: Transaction Pooler (6543) — stateless burst; min_size=0 (borrow/return),
    #   _transaction_pool_kwargs() enforces min_size=0 regardless, but preset
    #   reflects intent for clarity.
    # - discord/twitch: Session Pooler (5432) — long-lived stateful; min_size≥1
    #   to keep warm connections and enable prepared statements.
    _SERVICE_PRESETS: ClassVar[dict[str, dict]] = {
        "api": {"min_size": 0, "max_size": 10},
        "discord": {"min_size": 1, "max_size": 4},
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
    Handles Supabase Transaction vs Session Pooler detection,
    retry logic, and proper lifecycle management.
    """

    def __init__(self, database_url: str, config: PoolConfig | None = None):
        self.database_url = database_url
        self.config = config or PoolConfig()
        self._pool: asyncpg.Pool | None = None
        self._pooler_mode: str = "transaction" if ":6543" in database_url else "session"

    # ── Pool builders (separate code paths, no if/else) ──────────────

    async def _init_session_connection(self, conn: asyncpg.Connection) -> None:
        """Initialize new connections for Session Pooler.

        Sets session-level statement timeout. Only used with Session Pooler
        where session state is preserved across queries.
        """
        timeout_ms = int(self.config.command_timeout * 1000)
        await conn.execute(f"SET statement_timeout = {timeout_ms}")

    def _session_pool_kwargs(self) -> dict[str, Any]:
        """Build asyncpg.create_pool kwargs for Session Pooler (port 5432).

        - Prepared statements enabled (cache=100)
        - TCP keepalive via server_settings
        - Session-level init (SET statement_timeout)
        - Maintains min_size idle connections
        """
        cfg = self.config
        return {
            "dsn": self.database_url,
            "min_size": cfg.min_size,
            "max_size": cfg.max_size,
            "timeout": cfg.timeout,
            "command_timeout": cfg.command_timeout,
            "ssl": "require",
            "statement_cache_size": 100,
            "max_inactive_connection_lifetime": cfg.max_inactive_connection_lifetime,
            "server_settings": {
                "tcp_keepalives_idle": str(cfg.tcp_keepalives_idle),
                "tcp_keepalives_interval": str(cfg.tcp_keepalives_interval),
                "tcp_keepalives_count": str(cfg.tcp_keepalives_count),
            },
            "init": self._init_session_connection,
        }

    def _transaction_pool_kwargs(self) -> dict[str, Any]:
        """Build asyncpg.create_pool kwargs for Transaction Pooler (port 6543).

        PgBouncer in transaction mode:
        - No prepared statements (cache=0)
        - No server_settings (PgBouncer doesn't forward them)
        - No init callback (SET commands don't persist across queries)
        - min_size=0: don't hold idle connections (PgBouncer kills them)
        - max_inactive=0: release connections immediately after use
        """
        cfg = self.config
        return {
            "dsn": self.database_url,
            "min_size": 0,
            "max_size": cfg.max_size,
            "timeout": cfg.timeout,
            "command_timeout": cfg.command_timeout,
            "ssl": "require",
            "statement_cache_size": 0,
            "max_inactive_connection_lifetime": 0,
        }

    # ── Diagnostics ──────────────────────────────────────────────────

    def _diagnose_connection(self) -> None:
        """Log network-level diagnostics when DB connection fails."""
        parsed = urlparse(self.database_url)
        host = parsed.hostname or "unknown"
        port = parsed.port or 5432
        user = parsed.username or "unknown"

        logger.info(f"[DB Diag] host={host}, port={port}, user={user}")

        # 1. DNS resolution
        try:
            addrs = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
            families = {a[0].name for a in addrs}
            ips = {a[4][0] for a in addrs}
            logger.info(f"[DB Diag] DNS OK: {ips} (families: {families})")
        except socket.gaierror as e:
            logger.error(f"[DB Diag] DNS FAILED: {e}")
            return

        # 2. Raw TCP connection
        for addr in addrs[:2]:
            family, _, _, _, sockaddr = addr
            try:
                sock = socket.socket(family, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect(sockaddr)
                ip, port_ = str(sockaddr[0]), str(sockaddr[1])
                logger.info(f"[DB Diag] TCP OK: {ip}:{port_} ({family.name})")
                # 3. SSL handshake
                try:
                    ctx = _ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = _ssl.CERT_NONE
                    ssock = ctx.wrap_socket(sock, server_hostname=host)
                    logger.info(f"[DB Diag] SSL OK: {ssock.version()}")
                    ssock.close()
                except Exception as e:
                    logger.error(f"[DB Diag] SSL FAILED: {type(e).__name__}: {e}")
                    sock.close()
            except Exception as e:
                logger.error(
                    f"[DB Diag] TCP FAILED to {str(sockaddr[0])}:{str(sockaddr[1])}: {type(e).__name__}: {e}"
                )

    # ── Lifecycle ────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Initialize database connection pool with retry."""
        if self._pool is not None:
            logger.warning("Database pool already initialized")
            return

        # Select pool builder for detected pooler mode
        _builders = {
            "session": self._session_pool_kwargs,
            "transaction": self._transaction_pool_kwargs,
        }
        pool_kwargs = _builders[self._pooler_mode]()
        logger.info(f"Connecting with {self._pooler_mode} pooler mode")

        cfg = self.config
        for attempt in range(1, cfg.max_retries + 1):
            try:
                self._pool = await asyncpg.create_pool(**pool_kwargs)

                # Verify pool is usable
                async with self._pool.acquire() as conn:
                    await conn.fetchval("SELECT 1")

                effective_min = pool_kwargs.get("min_size", 0)
                effective_cache = pool_kwargs.get("statement_cache_size", 0)
                logger.info(
                    f"Database pool created and verified "
                    f"(mode={self._pooler_mode}, "
                    f"size={effective_min}-{cfg.max_size}, "
                    f"cache={effective_cache})"
                )
                return
            except Exception as e:
                if attempt < cfg.max_retries:
                    delay = cfg.retry_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"Database connection attempt {attempt}/{cfg.max_retries} failed: "
                        f"{type(e).__name__}: {e or repr(e)}, retrying in {delay}s..."
                    )
                    # Run diagnostics on first failure
                    if attempt == 1:
                        try:
                            self._diagnose_connection()
                        except Exception:
                            pass
                    if self._pool:
                        try:
                            await self._pool.close()
                        except Exception:
                            pass
                        self._pool = None
                    await asyncio.sleep(delay)
                else:
                    logger.exception(
                        f"Database connection failed after {cfg.max_retries} attempts: "
                        f"{type(e).__name__}: {e or repr(e)}"
                    )
                    raise

    async def disconnect(self) -> None:
        """Close database connection pool."""
        if self._pool is None:
            return

        try:
            await self._pool.close()
            self._pool = None
            logger.info("Database pool closed")
        except Exception as e:
            logger.exception(f"Error closing database pool: {e}")

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
    def pool(self) -> asyncpg.Pool:
        """Get the database connection pool. Raises if not initialized."""
        if self._pool is None:
            raise RuntimeError("Database pool not initialized. Call connect() first.")
        return self._pool

    async def get_connection(self) -> AsyncGenerator[asyncpg.Connection, None]:
        """Yield a connection from the pool (for dependency injection)."""
        async with self.pool.acquire() as conn:
            yield conn
