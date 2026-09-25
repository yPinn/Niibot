"""Create a one-time system Bot reset invite in a deployed API container."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import asyncpg

from scripts._lib import db_pool, ensure_backend_on_path, load_env, require_db_context

ensure_backend_on_path()
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))

from services.bot_account_service import (  # noqa: E402
    BotAccountService,
    BotInviteCreated,
    build_bot_invite_url,
)


@dataclass(frozen=True)
class InviteConfig:
    env: str
    frontend_url: str
    api_url: str
    owner_id: str
    bot_id: str
    token_encryption_key: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("stg", "prod"), required=True)
    parser.add_argument("-y", "--yes", action="store_true", help="confirm production mutation")
    return parser


def _public_origin(name: str, value: str) -> str:
    origin = value.rstrip("/")
    parsed = urlparse(origin)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or bool(parsed.params or parsed.query or parsed.fragment)
        or hostname in {"localhost", "127.0.0.1", "::1"}
        or hostname.endswith(".localhost")
    ):
        raise SystemExit(f"{name} must be a public HTTPS origin for stg/prod invites")
    return origin


def _config_from_env(env: str) -> InviteConfig:
    names = ("FRONTEND_URL", "API_URL", "OWNER_ID", "BOT_ID", "TWITCH_TOKEN_ENCRYPTION_KEY")
    values = {name: os.getenv(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise SystemExit(f"missing required environment values: {', '.join(missing)}")

    return InviteConfig(
        env=env,
        frontend_url=_public_origin("FRONTEND_URL", values["FRONTEND_URL"]),
        api_url=_public_origin("API_URL", values["API_URL"]),
        owner_id=values["OWNER_ID"],
        bot_id=values["BOT_ID"],
        token_encryption_key=values["TWITCH_TOKEN_ENCRYPTION_KEY"],
    )


async def _create_invite(pool: asyncpg.Pool, config: InviteConfig) -> BotInviteCreated:
    creator_user_id = await pool.fetchval(
        """
        SELECT i.user_id::text
          FROM identities AS i
          JOIN channels AS c ON c.channel_id = i.platform_user_id
         WHERE i.platform = 'twitch'
           AND i.platform_user_id = $1
        """,
        config.owner_id,
    )
    if not creator_user_id:
        raise SystemExit(
            "OWNER_ID is not initialized in this environment; "
            "sign in once through its frontend, then retry"
        )

    service = BotAccountService(pool, token_encryption_key=config.token_encryption_key)
    return await service.create_invite(
        channel_id=config.owner_id,
        creator_user_id=str(creator_user_id),
        purpose="system_default_reset",
        expected_bot_user_id=config.bot_id,
    )


async def _create_with_pool(config: InviteConfig) -> BotInviteCreated:
    async with db_pool(config.env, max_size=1) as pool:
        return await _create_invite(pool, config)


def _run_create(config: InviteConfig) -> BotInviteCreated:
    return asyncio.run(_create_with_pool(config))


def run(args: argparse.Namespace) -> int:
    require_db_context(args.env)
    load_env(args.env, service="api")
    if args.env == "prod" and not args.yes:
        raise SystemExit("production invite creation requires --yes")

    config = _config_from_env(args.env)
    created = _run_create(config)
    print(f"Invite URL: {build_bot_invite_url(config.frontend_url, created)}")
    print(f"Expires: {created.expires_at.isoformat()}")
    return 0


def main() -> None:
    raise SystemExit(run(build_parser().parse_args()))


if __name__ == "__main__":
    main()
