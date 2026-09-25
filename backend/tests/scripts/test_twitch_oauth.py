"""Security contracts for the standalone Twitch OAuth writer."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from scripts.twitch_ops import oauth as twitch_oauth  # noqa: E402

from shared.twitch_token_crypto import decrypt_twitch_token  # noqa: E402

_KEY = Fernet.generate_key().decode()


def test_oauth_cli_accepts_only_dev() -> None:
    assert twitch_oauth.build_parser().parse_args(["--env", "dev"]).env == "dev"
    with pytest.raises(SystemExit):
        twitch_oauth.build_parser().parse_args(["--env", "prod"])


async def test_save_token_persists_v1_envelopes(monkeypatch) -> None:
    conn = AsyncMock()
    monkeypatch.setattr(twitch_oauth.asyncpg, "connect", AsyncMock(return_value=conn))

    await twitch_oauth.save_token(
        "postgresql://database.test/niibot",
        "bot-1",
        "access-secret",
        "refresh-secret",
        ["user:bot", "user:write:chat"],
        "bot",
        encryption_key=_KEY,
    )

    sql, user_id, encrypted_access, encrypted_refresh, scopes, token_type, version = (
        conn.execute.await_args.args
    )
    assert "encryption_version" in sql
    assert "encryption_version = EXCLUDED.encryption_version" in sql
    assert (user_id, scopes, token_type, version) == (
        "bot-1",
        "user:bot user:write:chat",
        "bot",
        1,
    )
    assert "access-secret" not in (encrypted_access, encrypted_refresh)
    assert "refresh-secret" not in (encrypted_access, encrypted_refresh)
    assert decrypt_twitch_token(encrypted_access, version=version, key=_KEY) == "access-secret"
    assert decrypt_twitch_token(encrypted_refresh, version=version, key=_KEY) == "refresh-secret"
    conn.close.assert_awaited_once()
