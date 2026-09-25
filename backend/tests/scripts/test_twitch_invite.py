"""Security contracts for deployed Twitch bot reset invitations."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest
from scripts.twitch_ops import invite


def _config(**overrides: str) -> invite.InviteConfig:
    values = {
        "env": "stg",
        "frontend_url": "https://stg.niibot.example",
        "api_url": "https://api.stg.niibot.example",
        "owner_id": "owner-1",
        "bot_id": "bot-1",
        "token_encryption_key": "encryption-secret",
    }
    values.update(overrides)
    return invite.InviteConfig(**values)


def test_config_rejects_missing_values_without_printing_secrets(monkeypatch) -> None:
    monkeypatch.setenv("FRONTEND_URL", "https://stg.niibot.example")
    monkeypatch.setenv("API_URL", "https://api.stg.niibot.example")
    monkeypatch.setenv("OWNER_ID", "owner-1")
    monkeypatch.delenv("BOT_ID", raising=False)
    monkeypatch.setenv("TWITCH_TOKEN_ENCRYPTION_KEY", "do-not-print-this")

    with pytest.raises(SystemExit, match="BOT_ID") as exc:
        invite._config_from_env("stg")

    assert "do-not-print-this" not in str(exc.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://stg.niibot.example",
        "https://localhost:3000",
        "https://127.0.0.1:3000",
        "https://user:secret@stg.niibot.example",
        "https://stg.niibot.example/unexpected-path",
        "https://stg.niibot.example?target=prod",
    ],
)
@pytest.mark.parametrize("key", ["FRONTEND_URL", "API_URL"])
def test_config_rejects_non_public_deployed_origin(monkeypatch, key: str, url: str) -> None:
    monkeypatch.setenv("FRONTEND_URL", "https://stg.niibot.example")
    monkeypatch.setenv("API_URL", "https://api.stg.niibot.example")
    monkeypatch.setenv(key, url)
    monkeypatch.setenv("OWNER_ID", "owner-1")
    monkeypatch.setenv("BOT_ID", "bot-1")
    monkeypatch.setenv("TWITCH_TOKEN_ENCRYPTION_KEY", "encryption-secret")

    with pytest.raises(SystemExit, match="public HTTPS"):
        invite._config_from_env("stg")


async def test_create_invite_uses_owner_identity_and_expected_bot(monkeypatch) -> None:
    pool = AsyncMock()
    pool.fetchval.return_value = "4bc3ee00-43f5-40c5-80c1-9e4d59da0e95"
    created = invite.BotInviteCreated(
        id="invite-1",
        public_token="public-token",
        state_nonce="state-nonce",
        expires_at=datetime(2026, 9, 25, 1, 30, tzinfo=UTC),
    )
    create = AsyncMock(return_value=created)

    class FakeService:
        def __init__(self, actual_pool, *, token_encryption_key: str) -> None:
            assert actual_pool is pool
            assert token_encryption_key == "encryption-secret"
            self.create_invite = create

    monkeypatch.setattr(invite, "BotAccountService", FakeService)

    result = await invite._create_invite(pool, _config())

    assert result is created
    pool.fetchval.assert_awaited_once()
    create.assert_awaited_once_with(
        channel_id="owner-1",
        creator_user_id="4bc3ee00-43f5-40c5-80c1-9e4d59da0e95",
        purpose="system_default_reset",
        expected_bot_user_id="bot-1",
    )


async def test_create_invite_requires_existing_owner_identity() -> None:
    pool = AsyncMock()
    pool.fetchval.return_value = None

    with pytest.raises(SystemExit, match="sign in once"):
        await invite._create_invite(pool, _config())


def test_direct_prod_entry_requires_explicit_yes(monkeypatch) -> None:
    monkeypatch.setattr(invite, "require_db_context", lambda _env: None)
    monkeypatch.setattr(invite, "load_env", lambda _env, service=None: None)

    with pytest.raises(SystemExit, match="--yes"):
        invite.run(argparse.Namespace(env="prod", yes=False))


def test_host_entry_is_rejected_before_loading_env(monkeypatch) -> None:
    monkeypatch.delenv("NIIBOT_RUNTIME_CONTEXT", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    load = Mock()
    monkeypatch.setattr(invite, "load_env", load)

    with pytest.raises(SystemExit, match="must run in the matching container"):
        invite.run(argparse.Namespace(env="stg", yes=False))

    load.assert_not_called()


def test_mismatched_container_environment_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("NIIBOT_RUNTIME_CONTEXT", "container")
    monkeypatch.setenv("ENVIRONMENT", "production")

    with pytest.raises(SystemExit, match="does not match runtime"):
        invite.run(argparse.Namespace(env="stg", yes=False))


def test_success_prints_only_invite_url_and_expiry(monkeypatch, capsys) -> None:
    created = invite.BotInviteCreated(
        id="invite-1",
        public_token="public-token",
        state_nonce="state-nonce",
        expires_at=datetime(2026, 9, 25, 1, 30, tzinfo=UTC),
    )
    monkeypatch.setattr(invite, "require_db_context", lambda _env: None)
    monkeypatch.setattr(invite, "load_env", lambda _env, service=None: None)
    monkeypatch.setattr(invite, "_config_from_env", lambda _env: _config())
    monkeypatch.setattr(invite, "_run_create", lambda _config: created)
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "twitch-client-secret")

    assert invite.run(argparse.Namespace(env="stg", yes=False)) == 0

    output = capsys.readouterr().out
    assert output.splitlines() == [
        "Invite URL: https://stg.niibot.example/bot-invite/public-token?nonce=state-nonce",
        "Expires: 2026-09-25T01:30:00+00:00",
    ]
    assert "invite-1" not in output
    assert "encryption-secret" not in output
    assert "twitch-client-secret" not in output
