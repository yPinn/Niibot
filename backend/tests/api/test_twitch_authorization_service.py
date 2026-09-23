"""Credential lifecycle, tenant unlink, and broadcaster disconnect contracts."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from api.app import _twitch_authorization_loop
from api.services.twitch_api import (
    TokenRefreshResult,
    TokenRevocationResult,
    TokenValidationResult,
)
from api.services.twitch_authorization_service import (
    BotAccountInUseError,
    SystemBotProtectedError,
    TwitchAuthorizationService,
    TwitchCredentialInvalidError,
    TwitchProviderUnavailableError,
    TwitchScopeRequiredError,
)
from cryptography.fernet import Fernet

from shared.twitch_scopes import (
    BOT_CORE_SCOPES,
    BOT_SCOPES,
    BROADCASTER_CORE_SCOPES,
    BROADCASTER_SCOPES,
)
from shared.twitch_token_crypto import (
    TwitchTokenEncryptionNotConfiguredError,
    decrypt_twitch_token,
    encrypt_twitch_token,
)

_KEY = Fernet.generate_key().decode()
_NOW = datetime.now(UTC)


def _pool_with(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


def _tx_cm() -> MagicMock:
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=None)
    return tx


def _credential_row(*, user_id: str = "bot-1", token_type: str = "bot") -> dict:
    access, version = encrypt_twitch_token("access-secret", _KEY)
    refresh, _ = encrypt_twitch_token("refresh-secret", _KEY)
    return {
        "user_id": user_id,
        "token_type": token_type,
        "token": access,
        "refresh": refresh,
        "encryption_version": version,
        "requires_reauth": False,
        "last_checked_at": None,
        "last_validated_at": None,
        "invalidated_at": None,
        "validation_error_code": None,
    }


def _capability_row(
    *,
    broadcaster_scopes: str | None = " ".join(BROADCASTER_SCOPES),
    bot_scopes: str | None = " ".join(BOT_SCOPES),
) -> dict:
    return {
        "channel_id": "channel-1",
        "broadcaster_credential_user_id": "channel-1",
        "broadcaster_scopes": broadcaster_scopes,
        "broadcaster_requires_reauth": False,
        "broadcaster_last_validated_at": _NOW,
        "broadcaster_invalidated_at": None,
        "broadcaster_validation_error_code": None,
        "bot_user_id": "bot-1",
        "bot_credential_user_id": "bot-1",
        "bot_scopes": bot_scopes,
        "bot_requires_reauth": False,
        "bot_last_validated_at": _NOW,
        "bot_invalidated_at": None,
        "bot_validation_error_code": None,
    }


def _service(conn: AsyncMock, twitch: MagicMock) -> TwitchAuthorizationService:
    conn.transaction = MagicMock(return_value=_tx_cm())
    return TwitchAuthorizationService(
        _pool_with(conn),
        twitch_api=twitch,
        token_encryption_key=_KEY,
        client_id="client-1",
    )


@pytest.mark.asyncio
async def test_missing_encryption_key_still_allows_broadcaster_summary_reads():
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        "channel_id": "channel-1",
        "channel_name": "alice",
        "display_name": "Alice",
        "enabled": True,
        "token_user_id": "channel-1",
        "requires_reauth": False,
        "last_checked_at": None,
        "last_validated_at": None,
        "invalidated_at": None,
        "validation_error_code": None,
    }
    service = TwitchAuthorizationService(
        _pool_with(conn),
        twitch_api=MagicMock(),
        token_encryption_key="",
        client_id="client-1",
    )

    summary = await service.get_broadcaster_summary(channel_id="channel-1")

    assert summary.channel_name == "alice"
    assert summary.status == "not_checked"


@pytest.mark.asyncio
async def test_capability_snapshot_locks_only_missing_optional_scope():
    conn = AsyncMock()
    conn.fetchrow.return_value = _capability_row(
        broadcaster_scopes="channel:bot channel:manage:vips"
    )

    snapshot = await _service(conn, MagicMock()).get_capability_snapshot(
        channel_id="channel-1", system_bot_id="bot-1"
    )
    capabilities = {item.key: item for item in snapshot.capabilities}

    assert snapshot.broadcaster_status == "valid"
    assert capabilities["broadcaster_chat"].available is True
    assert capabilities["vip_management"].available is True
    assert capabilities["channel_points"].available is False
    assert capabilities["channel_points"].missing_scopes == ("channel:read:redemptions",)


@pytest.mark.asyncio
async def test_capability_snapshot_treats_missing_core_as_credential_reauth():
    conn = AsyncMock()
    conn.fetchrow.return_value = _capability_row(broadcaster_scopes="channel:manage:vips")

    snapshot = await _service(conn, MagicMock()).get_capability_snapshot(
        channel_id="channel-1", system_bot_id="bot-1"
    )
    broadcaster_features = [
        item for item in snapshot.capabilities if item.credential == "broadcaster"
    ]

    assert snapshot.broadcaster_status == "requires_reauthorization"
    assert all(item.available is False for item in broadcaster_features)


@pytest.mark.asyncio
async def test_require_capability_returns_available_feature():
    conn = AsyncMock()
    conn.fetchrow.return_value = _capability_row()

    health = await _service(conn, MagicMock()).require_capability(
        channel_id="channel-1",
        system_bot_id="bot-1",
        capability_key="moderator_management",
    )

    assert health.available is True


@pytest.mark.asyncio
async def test_require_capability_classifies_optional_scope_without_global_reauth():
    conn = AsyncMock()
    conn.fetchrow.return_value = _capability_row(broadcaster_scopes="channel:bot")

    with pytest.raises(TwitchScopeRequiredError) as caught:
        await _service(conn, MagicMock()).require_capability(
            channel_id="channel-1",
            system_bot_id="bot-1",
            capability_key="moderator_management",
        )

    assert caught.value.response_headers == {}
    assert caught.value.fields == {
        "capability": "moderator_management",
        "missing_scopes": "channel:manage:moderators",
    }


@pytest.mark.asyncio
async def test_require_capability_classifies_invalid_credential_for_global_reauth():
    conn = AsyncMock()
    conn.fetchrow.return_value = _capability_row(broadcaster_scopes="channel:manage:moderators")

    with pytest.raises(TwitchCredentialInvalidError) as caught:
        await _service(conn, MagicMock()).require_capability(
            channel_id="channel-1",
            system_bot_id="bot-1",
            capability_key="moderator_management",
        )

    assert caught.value.response_headers == {"X-Reauth-Required": "true"}


@pytest.mark.asyncio
async def test_require_capability_classifies_provider_outage_without_reauth():
    conn = AsyncMock()
    row = _capability_row()
    row["broadcaster_validation_error_code"] = "provider_unavailable"
    conn.fetchrow.return_value = row

    with pytest.raises(TwitchProviderUnavailableError):
        await _service(conn, MagicMock()).require_capability(
            channel_id="channel-1",
            system_bot_id="bot-1",
            capability_key="moderator_management",
        )


@pytest.mark.asyncio
async def test_missing_encryption_key_rejects_credential_check_before_database_access():
    conn = AsyncMock()
    service = TwitchAuthorizationService(
        _pool_with(conn),
        twitch_api=MagicMock(),
        token_encryption_key="",
        client_id="client-1",
    )

    with pytest.raises(TwitchTokenEncryptionNotConfiguredError):
        await service.check_credential(
            user_id="bot-1",
            token_type="bot",
            required_scopes=set(BOT_SCOPES),
        )

    conn.fetchrow.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_encryption_key_disables_background_reconciliation(caplog):
    db_manager = MagicMock(is_connected=True)
    settings = SimpleNamespace(twitch_token_encryption_key="", client_id="client-1")

    await _twitch_authorization_loop(db_manager, settings)

    assert "disabled" in caplog.text.lower()
    db_manager.pool.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_background_loop_drains_one_credential_per_second_without_batches():
    db_manager = MagicMock(is_connected=True)
    settings = SimpleNamespace(twitch_token_encryption_key=_KEY, client_id="client-1")
    service = MagicMock()
    service.check_due_credentials = AsyncMock(return_value=1)

    with (
        patch(
            "api.app.TwitchAuthorizationService",
            return_value=service,
        ),
        patch("api.app.get_twitch_api", return_value=MagicMock()),
        patch("api.app.asyncio.sleep", new=AsyncMock(side_effect=asyncio.CancelledError)) as sleep,
    ):
        await _twitch_authorization_loop(db_manager, settings)

    service.check_due_credentials.assert_awaited_once_with(limit=1)
    sleep.assert_awaited_once_with(1.0)


@pytest.mark.asyncio
async def test_transient_validation_failure_never_marks_reauth_or_disables_channel():
    conn = AsyncMock()
    conn.fetchrow.return_value = _credential_row(user_id="channel-1", token_type="broadcaster")
    twitch = MagicMock()
    twitch.validate_token_details = AsyncMock(
        return_value=TokenValidationResult(status="unavailable", error_code="provider_unavailable")
    )

    result = await _service(conn, twitch).check_credential(
        user_id="channel-1",
        token_type="broadcaster",
        required_scopes=set(BROADCASTER_SCOPES),
    )

    assert result.status == "temporarily_unavailable"
    statements = [call.args[0] for call in conn.execute.await_args_list]
    assert any("last_checked_at" in sql for sql in statements)
    assert all("requires_reauth = TRUE" not in sql for sql in statements)
    assert all("UPDATE channels" not in sql for sql in statements)


@pytest.mark.asyncio
async def test_provider_outage_does_not_hide_an_existing_reauthorization_requirement():
    conn = AsyncMock()
    row = _credential_row(user_id="channel-1", token_type="broadcaster")
    row.update(
        requires_reauth=True,
        invalidated_at=_NOW,
        validation_error_code="missing_scopes",
    )
    conn.fetchrow.return_value = row
    twitch = MagicMock()
    twitch.validate_token_details = AsyncMock(
        return_value=TokenValidationResult(status="unavailable", error_code="provider_unavailable")
    )

    result = await _service(conn, twitch).check_credential(
        user_id="channel-1",
        token_type="broadcaster",
        required_scopes=set(BROADCASTER_SCOPES),
    )

    assert result.status == "requires_reauthorization"
    assert result.error_code == "missing_scopes"


@pytest.mark.asyncio
async def test_background_reconciliation_defers_unexpected_failures_to_avoid_starvation():
    conn = AsyncMock()
    service = _service(conn, MagicMock())
    service.claim_due_credentials = AsyncMock(return_value=[("bot-1", "bot")])  # type: ignore[attr-defined,method-assign]
    service.check_credential = AsyncMock(side_effect=RuntimeError("bad ciphertext"))  # type: ignore[method-assign]

    checked = await service.check_due_credentials(limit=25)

    assert checked == 1
    deferred = next(
        call.args for call in conn.execute.await_args_list if "next_validation_at" in call.args[0]
    )
    assert deferred[1:] == ("bot-1", "bot")


@pytest.mark.asyncio
async def test_background_reconciliation_validates_only_runtime_core_scopes():
    conn = AsyncMock()
    service = _service(conn, MagicMock())
    service.claim_due_credentials = AsyncMock(  # type: ignore[attr-defined,method-assign]
        return_value=[("bot-1", "bot"), ("channel-1", "broadcaster")]
    )
    service.check_credential = AsyncMock()  # type: ignore[method-assign]

    checked = await service.check_due_credentials(limit=25)

    assert checked == 2
    assert service.check_credential.await_args_list[0].kwargs["required_scopes"] == set(
        BOT_CORE_SCOPES
    )
    assert service.check_credential.await_args_list[1].kwargs["required_scopes"] == set(
        BROADCASTER_CORE_SCOPES
    )


@pytest.mark.asyncio
async def test_due_credentials_are_atomically_claimed_across_replicas():
    conn = AsyncMock()
    conn.fetch.return_value = [
        {"user_id": "bot-1", "token_type": "bot"},
        {"user_id": "channel-1", "token_type": "broadcaster"},
    ]
    service = _service(conn, MagicMock())

    claimed = await service.claim_due_credentials(limit=2)

    assert claimed == [("bot-1", "bot"), ("channel-1", "broadcaster")]
    sql, limit = conn.fetch.await_args.args
    assert limit == 2
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "next_validation_at IS NULL" in sql
    assert "next_validation_at <= NOW()" in sql
    assert "UPDATE tokens" in sql
    assert "INTERVAL '5 minutes'" in sql


@pytest.mark.asyncio
async def test_successful_validation_schedules_the_next_hourly_check():
    conn = AsyncMock()
    conn.fetchrow.return_value = _credential_row()
    twitch = MagicMock()
    twitch.validate_token_details = AsyncMock(
        return_value=TokenValidationResult(
            status="valid",
            client_id="client-1",
            login="bot_one",
            user_id="bot-1",
            scopes=frozenset(BOT_SCOPES),
            expires_in=3600,
        )
    )

    await _service(conn, twitch).check_credential(
        user_id="bot-1", token_type="bot", required_scopes=set(BOT_SCOPES)
    )

    health_sql = next(
        call.args[0] for call in conn.execute.await_args_list if "last_validated_at" in call.args[0]
    )
    assert "next_validation_at = NOW() + INTERVAL '55 minutes'" in health_sql


@pytest.mark.asyncio
async def test_provider_outage_retries_soon_without_refresh_or_reauth():
    conn = AsyncMock()
    conn.fetchrow.return_value = _credential_row(user_id="channel-1", token_type="broadcaster")
    twitch = MagicMock()
    twitch.validate_token_details = AsyncMock(
        return_value=TokenValidationResult(status="unavailable", error_code="provider_unavailable")
    )

    await _service(conn, twitch).check_credential(
        user_id="channel-1",
        token_type="broadcaster",
        required_scopes=set(BROADCASTER_SCOPES),
    )

    transient_sql = next(
        call.args[0]
        for call in conn.execute.await_args_list
        if "provider_unavailable" in call.args[0]
    )
    assert "next_validation_at = NOW() + INTERVAL '5 minutes'" in transient_sql
    twitch.refresh_access_token.assert_not_called()


@pytest.mark.asyncio
async def test_transient_refresh_failure_never_marks_reauth_or_disables_channel():
    conn = AsyncMock()
    conn.fetchrow.return_value = _credential_row(user_id="channel-1", token_type="broadcaster")
    twitch = MagicMock()
    twitch.validate_token_details = AsyncMock(
        return_value=TokenValidationResult(status="invalid", error_code="invalid_token")
    )
    twitch.refresh_access_token = AsyncMock(
        return_value=TokenRefreshResult(
            success=False,
            error="malformed success response",
            error_code="provider_unavailable",
        )
    )

    result = await _service(conn, twitch).check_credential(
        user_id="channel-1",
        token_type="broadcaster",
        required_scopes=set(BROADCASTER_SCOPES),
    )

    assert result.status == "temporarily_unavailable"
    statements = [call.args[0] for call in conn.execute.await_args_list]
    assert all("requires_reauth = TRUE" not in sql for sql in statements)
    assert all("UPDATE channels" not in sql for sql in statements)


@pytest.mark.asyncio
async def test_valid_token_requires_matching_identity_client_and_scopes():
    conn = AsyncMock()
    conn.fetchrow.return_value = _credential_row()
    twitch = MagicMock()
    twitch.validate_token_details = AsyncMock(
        return_value=TokenValidationResult(
            status="valid",
            client_id="client-1",
            login="bot_one",
            user_id="bot-1",
            scopes=frozenset(BOT_SCOPES),
            expires_in=3600,
        )
    )

    result = await _service(conn, twitch).check_credential(
        user_id="bot-1", token_type="bot", required_scopes=set(BOT_SCOPES)
    )

    assert result.status == "valid"
    health_write = next(
        call.args for call in conn.execute.await_args_list if "last_validated_at" in call.args[0]
    )
    assert "requires_reauth = FALSE" in health_write[0]
    account_lock = next(
        call.args
        for call in conn.execute.await_args_list
        if "FROM bot_accounts" in call.args[0] and "FOR UPDATE" in call.args[0]
    )
    assert account_lock[1] == "bot-1"
    assert any("pg_advisory_xact_lock" in call.args[0] for call in conn.execute.await_args_list)
    assert any(
        "scopes = $3" in call.args[0] and call.args[3] == " ".join(sorted(BOT_SCOPES))
        for call in conn.execute.await_args_list
    )


@pytest.mark.asyncio
async def test_invalid_access_token_refreshes_rotates_and_revalidates_atomically():
    conn = AsyncMock()
    conn.fetchrow.return_value = _credential_row()
    twitch = MagicMock()
    twitch.validate_token_details = AsyncMock(
        side_effect=[
            TokenValidationResult(status="invalid", error_code="invalid_token"),
            TokenValidationResult(
                status="valid",
                client_id="client-1",
                login="bot_one",
                user_id="bot-1",
                scopes=frozenset(BOT_SCOPES),
                expires_in=3600,
            ),
        ]
    )
    twitch.refresh_access_token = AsyncMock(
        return_value=TokenRefreshResult(
            success=True,
            access_token="new-access",
            refresh_token="new-refresh",
        )
    )

    result = await _service(conn, twitch).check_credential(
        user_id="bot-1", token_type="bot", required_scopes=set(BOT_SCOPES)
    )

    assert result.status == "valid"
    token_write = next(
        call.args for call in conn.execute.await_args_list if "token = $3" in call.args[0]
    )
    assert "credential_revision = credential_revision + 1" in token_write[0]
    assert decrypt_twitch_token(token_write[3], version=1, key=_KEY) == "new-access"
    assert decrypt_twitch_token(token_write[4], version=1, key=_KEY) == "new-refresh"
    notify_call = next(
        call.args for call in conn.execute.await_args_list if "pg_notify($1, $2)" in call.args[0]
    )
    assert notify_call[1] == "bot_token_updated"
    assert '"user_id": "bot-1"' in notify_call[2]


@pytest.mark.asyncio
async def test_broadcaster_refresh_relies_on_revision_trigger_without_duplicate_notify():
    conn = AsyncMock()
    conn.fetchrow.return_value = _credential_row(user_id="channel-1", token_type="broadcaster")
    twitch = MagicMock()
    twitch.validate_token_details = AsyncMock(
        side_effect=[
            TokenValidationResult(status="invalid", error_code="invalid_token"),
            TokenValidationResult(
                status="valid",
                client_id="client-1",
                login="alice",
                user_id="channel-1",
                scopes=frozenset(BROADCASTER_SCOPES),
                expires_in=3600,
            ),
        ]
    )
    twitch.refresh_access_token = AsyncMock(
        return_value=TokenRefreshResult(
            success=True,
            access_token="new-access",
            refresh_token="new-refresh",
        )
    )

    result = await _service(conn, twitch).check_credential(
        user_id="channel-1",
        token_type="broadcaster",
        required_scopes=set(BROADCASTER_SCOPES),
    )

    assert result.status == "valid"
    assert all("pg_notify($1, $2)" not in call.args[0] for call in conn.execute.await_args_list)


@pytest.mark.asyncio
async def test_identity_mismatch_definitely_invalidates_and_falls_back_custom_bot():
    conn = AsyncMock()
    conn.fetchrow.return_value = _credential_row()
    twitch = MagicMock()
    twitch.validate_token_details = AsyncMock(
        return_value=TokenValidationResult(
            status="valid",
            client_id="client-1",
            login="other",
            user_id="attacker",
            scopes=frozenset(BOT_SCOPES),
            expires_in=3600,
        )
    )

    result = await _service(conn, twitch).check_credential(
        user_id="bot-1", token_type="bot", required_scopes=set(BOT_SCOPES)
    )

    assert result.status == "requires_reauthorization"
    assert result.error_code == "identity_mismatch"
    statements = [call.args[0] for call in conn.execute.await_args_list]
    assert any("requires_reauth = TRUE" in sql for sql in statements)
    assert any("UPDATE channel_bot_settings" in sql for sql in statements)
    assert any("pg_notify('bot_selection_changed'" in sql for sql in statements)


@pytest.mark.asyncio
async def test_existing_unchecked_broadcaster_token_is_not_mislabeled_as_disconnected():
    conn = AsyncMock()
    conn.fetchrow.return_value = {
        "channel_id": "channel-1",
        "channel_name": "alice",
        "display_name": "Alice",
        "enabled": True,
        "token_user_id": "channel-1",
        "requires_reauth": False,
        "last_checked_at": None,
        "last_validated_at": None,
        "invalidated_at": None,
        "validation_error_code": None,
    }

    summary = await _service(conn, MagicMock()).get_broadcaster_summary(channel_id="channel-1")

    assert summary.status == "not_checked"


@pytest.mark.asyncio
async def test_unlink_rejects_system_or_currently_selected_bot():
    for account_row, mapping_row, error in (
        (
            {"is_system_default": True, "platform_user_id": "bot-1"},
            None,
            SystemBotProtectedError,
        ),
        (
            {"is_system_default": False, "platform_user_id": "bot-1"},
            {"is_active": True, "is_desired": False, "mapping_count": 1},
            BotAccountInUseError,
        ),
    ):
        conn = AsyncMock()
        conn.transaction = MagicMock(return_value=_tx_cm())
        conn.fetchrow.side_effect = (
            [account_row] if mapping_row is None else [account_row, mapping_row]
        )
        twitch = MagicMock()

        with pytest.raises(error):
            await _service(conn, twitch).unlink_bot_from_tenant(
                channel_id="channel-1", bot_user_id="bot-1", actor_user_id="user-1"
            )


@pytest.mark.asyncio
async def test_last_tenant_unlink_removes_local_credential_then_revokes_upstream():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    row = _credential_row()
    conn.fetchrow.side_effect = [
        {
            "is_system_default": False,
            "platform_user_id": "bot-1",
        },
        {"is_active": False, "is_desired": False, "mapping_count": 1},
        {
            "token": row["token"],
            "encryption_version": row["encryption_version"],
        },
    ]
    twitch = MagicMock()
    twitch.revoke_access_token = AsyncMock(return_value=TokenRevocationResult(status="revoked"))

    result = await _service(conn, twitch).unlink_bot_from_tenant(
        channel_id="channel-1", bot_user_id="bot-1", actor_user_id="user-1"
    )

    assert result.credential_retained is False
    assert result.upstream_revoke_confirmed is True
    statements = [call.args[0] for call in conn.execute.await_args_list]
    assert any("DELETE FROM channel_bot_accounts" in sql for sql in statements)
    assert any("DELETE FROM tokens" in sql for sql in statements)
    twitch.revoke_access_token.assert_awaited_once_with("access-secret")

    account_lock_sql = conn.fetchrow.await_args_list[0].args[0]
    mapping_count_sql = conn.fetchrow.await_args_list[1].args[0]
    assert "FOR UPDATE" in account_lock_sql
    assert "COUNT(*)" not in account_lock_sql
    assert "COUNT(*)" in mapping_count_sql


@pytest.mark.asyncio
async def test_unlink_keeps_shared_credential_while_another_tenant_mapping_exists():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    conn.fetchrow.side_effect = [
        {"is_system_default": False, "platform_user_id": "bot-1"},
        {"is_active": False, "is_desired": False, "mapping_count": 2},
    ]
    twitch = MagicMock()
    twitch.revoke_access_token = AsyncMock()

    result = await _service(conn, twitch).unlink_bot_from_tenant(
        channel_id="channel-1", bot_user_id="bot-1", actor_user_id="user-1"
    )

    assert result.credential_retained is True
    statements = [call.args[0] for call in conn.execute.await_args_list]
    assert all("DELETE FROM tokens" not in sql for sql in statements)
    twitch.revoke_access_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_last_tenant_unlink_without_token_still_marks_local_credential_removed():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    conn.fetchrow.side_effect = [
        {"is_system_default": False, "platform_user_id": "bot-1"},
        {"is_active": False, "is_desired": False, "mapping_count": 1},
        None,
    ]
    twitch = MagicMock()
    twitch.revoke_access_token = AsyncMock()

    result = await _service(conn, twitch).unlink_bot_from_tenant(
        channel_id="channel-1", bot_user_id="bot-1", actor_user_id="user-1"
    )

    assert result.credential_retained is False
    statements = [call.args[0] for call in conn.execute.await_args_list]
    assert any("DELETE FROM tokens" in sql for sql in statements)
    assert any("UPDATE bot_accounts" in sql for sql in statements)
    twitch.revoke_access_token.assert_not_awaited()


@pytest.mark.asyncio
async def test_broadcaster_disconnect_stops_channel_invalidates_sessions_and_keeps_history():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    row = _credential_row(user_id="channel-1", token_type="broadcaster")
    conn.fetchrow.return_value = row
    twitch = MagicMock()
    twitch.revoke_access_token = AsyncMock(
        return_value=TokenRevocationResult(status="unavailable", error_code="provider_unavailable")
    )

    result = await _service(conn, twitch).disconnect_broadcaster(
        channel_id="channel-1", owner_user_id="user-1"
    )

    assert result.upstream_revoke_confirmed is False
    statements = [call.args[0] for call in conn.execute.await_args_list]
    assert any("UPDATE channels" in sql and "enabled = FALSE" in sql for sql in statements)
    assert any("session_version = session_version + 1" in sql for sql in statements)
    assert any("DELETE FROM tokens" in sql for sql in statements)
    assert all("DELETE FROM users" not in sql for sql in statements)
    assert all("DELETE FROM channels" not in sql for sql in statements)


@pytest.mark.asyncio
async def test_broadcaster_disconnect_stays_successful_after_unexpected_revoke_error():
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=_tx_cm())
    conn.fetchrow.return_value = _credential_row(user_id="channel-1", token_type="broadcaster")
    twitch = MagicMock()
    twitch.revoke_access_token = AsyncMock(side_effect=RuntimeError("provider client failed"))

    result = await _service(conn, twitch).disconnect_broadcaster(
        channel_id="channel-1", owner_user_id="user-1"
    )

    assert result.credential_retained is False
    assert result.upstream_revoke_confirmed is False
