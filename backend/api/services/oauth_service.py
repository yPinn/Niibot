"""OAuth helper functions — user find/create and account linking."""

import base64
import json
import logging

from asyncpg import Pool

logger = logging.getLogger(__name__)


async def find_or_create_user(
    pool: Pool,
    platform: str,
    platform_user_id: str,
    username: str,
    display_name: str | None = None,
    avatar: str | None = None,
) -> str:
    """Find existing user by linked account or create a new one.

    Uses a transaction to prevent TOCTOU race on concurrent OAuth callbacks.
    Returns users.id as string.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT user_id FROM user_linked_accounts"
                " WHERE platform = $1 AND platform_user_id = $2",
                platform,
                platform_user_id,
            )
            if row:
                return str(row["user_id"])

            user_row = await conn.fetchrow(
                "INSERT INTO users (display_name, avatar) VALUES ($1, $2) RETURNING id",
                display_name or username,
                avatar,
            )
            user_id = str(user_row["id"])

            await conn.execute(
                "INSERT INTO user_linked_accounts"
                " (user_id, platform, platform_user_id, username)"
                " VALUES ($1, $2, $3, $4)",
                user_row["id"],
                platform,
                platform_user_id,
                username,
            )

    logger.info(f"Created user {user_id} for {platform}:{platform_user_id} ({username})")
    return user_id


async def link_account(
    pool: Pool,
    user_id: str,
    platform: str,
    platform_user_id: str,
    username: str,
) -> tuple[bool, str | None]:
    """Link a platform account to an existing user.

    Returns (success, error_code).
    """
    row = await pool.fetchrow(
        "SELECT user_id FROM user_linked_accounts WHERE platform = $1 AND platform_user_id = $2",
        platform,
        platform_user_id,
    )
    if row:
        existing_uid = str(row["user_id"])
        if existing_uid == user_id:
            return True, None  # Already linked to this user — idempotent
        return False, "already_linked"

    row = await pool.fetchrow(
        "SELECT platform_user_id FROM user_linked_accounts"
        " WHERE user_id = $1::uuid AND platform = $2",
        user_id,
        platform,
    )
    if row:
        return False, "platform_already_linked"

    await pool.execute(
        "INSERT INTO user_linked_accounts (user_id, platform, platform_user_id, username)"
        " VALUES ($1::uuid, $2, $3, $4)",
        user_id,
        platform,
        platform_user_id,
        username,
    )
    logger.info(f"Linked {platform}:{platform_user_id} ({username}) to user {user_id}")
    return True, None


def encode_oauth_state(mode: str, user_id: str | None = None) -> str:
    """Encode OAuth state as base64 JSON."""
    data: dict = {"mode": mode}
    if user_id:
        data["uid"] = user_id
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def decode_oauth_state(state: str | None) -> dict:
    """Decode OAuth state from base64 JSON. Returns {"mode": "login"} on failure."""
    if not state:
        return {"mode": "login"}
    try:
        return json.loads(base64.urlsafe_b64decode(state.encode()).decode())
    except Exception:
        return {"mode": "login"}
