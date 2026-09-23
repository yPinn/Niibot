"""Bot invite API boundaries: owner creation, public consent, and no-session callback."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-auth-router-tests")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("BOT_ID", "bot-test")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.dependencies import (
    get_bot_account_service,
    get_current_user_id,
    get_twitch_api,
    get_twitch_authorization_service,
    require_owner,
    require_tenant_access,
    require_tenant_owner,
)
from core.error_handlers import register_exception_handlers
from routers.bot_accounts_router import router
from services.bot_account_service import (
    BotAccountSummary,
    BotAuthorizationResult,
    BotInviteCreated,
    BotInviteStatus,
    PublicBotInviteSummary,
)
from services.oauth_service import decode_oauth_state, encode_oauth_state
from services.tenant_service import TenantContext
from services.twitch_authorization_service import (
    AuthorizationRemovalResult,
    BroadcasterAuthorizationSummary,
    CapabilityHealth,
    CredentialHealth,
    TwitchCapabilitySnapshot,
)
from shared.twitch_scopes import BOT_CORE_SCOPES, BOT_SCOPES, BROADCASTER_CORE_SCOPES

_NOW = datetime.now(UTC)
_USER_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_STATE_NONCE = "state-nonce-123456"


def _client(
    service: MagicMock,
    twitch: MagicMock | None = None,
    authorization: MagicMock | None = None,
) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_bot_account_service] = lambda: service
    app.dependency_overrides[get_twitch_api] = lambda: twitch or MagicMock()
    app.dependency_overrides[get_twitch_authorization_service] = lambda: (
        authorization or MagicMock()
    )
    app.dependency_overrides[require_tenant_owner] = lambda: TenantContext(
        channel_id="channel-a", user_id=_USER_ID, role="owner"
    )
    app.dependency_overrides[require_tenant_access] = lambda: TenantContext(
        channel_id="channel-a", user_id=_USER_ID, role="owner"
    )
    app.dependency_overrides[require_owner] = lambda: "channel-a"
    app.dependency_overrides[get_current_user_id] = lambda: _USER_ID
    return TestClient(app, raise_server_exceptions=False)


def test_owner_creates_shareable_invite_url_without_exposing_credentials():
    service = MagicMock()
    service.create_invite = AsyncMock(
        return_value=BotInviteCreated(
            id="11111111-2222-3333-4444-555555555555",
            public_token="opaque",
            state_nonce=_STATE_NONCE,
            expires_at=_NOW + timedelta(minutes=30),
        )
    )

    response = _client(service).post(
        "/api/tenants/channel-a/bot-accounts/invites",
        headers={"X-Niibot-Action": "bot-account-management"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["invite_id"] == "11111111-2222-3333-4444-555555555555"
    assert f"/bot-invite/opaque?nonce={_STATE_NONCE}" in body["public_url"]
    assert "access_token" not in body
    assert "refresh_token" not in body
    service.create_invite.assert_awaited_once_with(
        channel_id="channel-a",
        creator_user_id=_USER_ID,
    )


def test_system_owner_creates_expected_account_reset_invite():
    service = MagicMock()
    service.create_invite = AsyncMock(
        return_value=BotInviteCreated(
            id="11111111-2222-3333-4444-555555555555",
            public_token="opaque",
            state_nonce=_STATE_NONCE,
            expires_at=_NOW + timedelta(minutes=30),
        )
    )

    response = _client(service).post(
        "/api/admin/bot-accounts/system-default/reset-invite",
        headers={"X-Niibot-Action": "bot-account-management"},
    )

    assert response.status_code == 201
    service.create_invite.assert_awaited_once_with(
        channel_id="channel-a",
        creator_user_id=_USER_ID,
        purpose="system_default_reset",
        expected_bot_user_id="bot-test",
    )


def test_owner_reauthorizes_only_the_named_tenant_bot_account():
    service = MagicMock()
    service.create_invite = AsyncMock(
        return_value=BotInviteCreated(
            id="11111111-2222-3333-4444-555555555555",
            public_token="opaque",
            state_nonce=_STATE_NONCE,
            expires_at=_NOW + timedelta(minutes=30),
        )
    )

    response = _client(service).post(
        "/api/tenants/channel-a/bot-accounts/bot-b/reauthorize-invite",
        headers={"X-Niibot-Action": "bot-account-management"},
    )

    assert response.status_code == 201
    service.create_invite.assert_awaited_once_with(
        channel_id="channel-a",
        creator_user_id=_USER_ID,
        purpose="reauthorize",
        expected_bot_user_id="bot-b",
    )


def test_public_consent_summary_contains_only_safe_tenant_and_scope_data():
    service = MagicMock()
    service.get_public_invite = AsyncMock(
        return_value=PublicBotInviteSummary(
            invite_id="11111111-2222-3333-4444-555555555555",
            channel_name="alice",
            display_name="Alice",
            purpose="link_new",
            status="pending",
            expires_at=_NOW + timedelta(minutes=20),
        )
    )
    twitch = MagicMock()
    twitch.generate_oauth_url.return_value = "https://id.twitch.tv/oauth2/authorize?safe=1"

    response = _client(service, twitch).get(f"/api/public/bot-invites/opaque?nonce={_STATE_NONCE}")

    assert response.status_code == 200
    assert response.json() == {
        "channel_name": "alice",
        "display_name": "Alice",
        "purpose": "link_new",
        "status": "pending",
        "expires_at": response.json()["expires_at"],
        "required_scopes": BOT_SCOPES,
        "oauth_url": "https://id.twitch.tv/oauth2/authorize?safe=1",
    }
    service.get_public_invite.assert_awaited_once_with(
        public_token="opaque", state_nonce=_STATE_NONCE
    )
    _, kwargs = twitch.generate_oauth_url.call_args
    assert kwargs["scopes"] == BOT_SCOPES
    assert kwargs["redirect_path"] == "/api/auth/twitch/bot/callback"
    decoded = decode_oauth_state(
        kwargs["state"], secret="test-jwt-secret-key-for-auth-router-tests"
    )
    assert decoded["uid"] == f"11111111-2222-3333-4444-555555555555.{_STATE_NONCE}"
    assert "opaque" not in decoded["uid"]


def test_tenant_bot_list_combines_only_system_default_and_explicit_mappings():
    service = MagicMock()
    service.get_system_default = AsyncMock(
        return_value=BotAccountSummary(
            platform_user_id="niibot",
            login="niibot_",
            display_name="Niibot",
            avatar=None,
            requires_reauth=False,
            last_validated_at=_NOW,
            revoked_at=None,
        )
    )
    service.list_for_tenant = AsyncMock(
        return_value=[
            BotAccountSummary(
                platform_user_id="bot-b",
                login="bot_b",
                display_name="Bot B",
                avatar=None,
                requires_reauth=False,
                last_validated_at=_NOW,
                revoked_at=None,
            )
        ]
    )

    response = _client(service).get("/api/tenants/channel-a/bot-accounts")

    assert response.status_code == 200
    assert [
        (item["platform_user_id"], item["is_system_default"])
        for item in response.json()["accounts"]
    ] == [
        ("niibot", True),
        ("bot-b", False),
    ]
    service.list_for_tenant.assert_awaited_once_with("channel-a")


def test_owner_polls_invite_status_without_receiving_invite_secrets():
    service = MagicMock()
    service.get_invite_status = AsyncMock(
        return_value=BotInviteStatus(
            id="11111111-2222-3333-4444-555555555555",
            status="authorized",
            expires_at=_NOW + timedelta(minutes=20),
            consumed_at=_NOW,
            account=BotAccountSummary(
                platform_user_id="bot-b",
                login="bot_b",
                display_name="Bot B",
                avatar=None,
                requires_reauth=False,
                last_validated_at=_NOW,
                revoked_at=None,
            ),
        )
    )

    response = _client(service).get(
        "/api/tenants/channel-a/bot-accounts/invites/11111111-2222-3333-4444-555555555555"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "authorized"
    assert response.json()["account"]["platform_user_id"] == "bot-b"
    assert "public_token" not in response.text
    assert "state_nonce" not in response.text


def test_bot_callback_updates_registry_but_never_creates_a_dashboard_session():
    service = MagicMock()
    service.authorize_invite = AsyncMock(
        return_value=BotAuthorizationResult(
            channel_id="channel-a",
            platform_user_id="bot-b",
            login="bot_b",
            display_name="Bot B",
            avatar=None,
        )
    )
    twitch = MagicMock()
    twitch.exchange_code_for_token = AsyncMock(
        return_value=(
            True,
            None,
            {
                "user_id": "bot-b",
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
                "scopes": " ".join(BOT_SCOPES),
            },
        )
    )
    twitch.get_user_info = AsyncMock(
        return_value={
            "id": "bot-b",
            "name": "bot_b",
            "display_name": "Bot B",
            "avatar": None,
        }
    )
    state = encode_oauth_state(
        "bot_authorization",
        f"11111111-2222-3333-4444-555555555555.{_STATE_NONCE}",
        secret="test-jwt-secret-key-for-auth-router-tests",
    )

    response = _client(service, twitch).get(
        "/api/auth/twitch/bot/callback",
        params={"code": "oauth-code", "state": state},
        follow_redirects=False,
    )

    assert response.status_code in {302, 303, 307}
    assert response.headers["location"].endswith("/bot-auth/result?status=success")
    assert "set-cookie" not in response.headers
    service.authorize_invite.assert_awaited_once_with(
        invite_id="11111111-2222-3333-4444-555555555555",
        state_nonce=_STATE_NONCE,
        platform_user_id="bot-b",
        access_token="access-secret",
        refresh_token="refresh-secret",
        scopes=set(BOT_SCOPES),
        login="bot_b",
        display_name="Bot B",
        avatar=None,
    )


def test_bot_callback_rejects_tampered_state_before_token_exchange():
    service = MagicMock()
    twitch = MagicMock()
    twitch.exchange_code_for_token = AsyncMock()

    response = _client(service, twitch).get(
        "/api/auth/twitch/bot/callback",
        params={"code": "oauth-code", "state": "tampered"},
        follow_redirects=False,
    )

    assert response.status_code in {302, 303, 307}
    assert "status=error" in response.headers["location"]
    twitch.exchange_code_for_token.assert_not_awaited()


def test_owner_can_recheck_one_tenant_bot_authorization():
    service = MagicMock()
    service.assert_available_to_tenant = AsyncMock()
    authorization = MagicMock()
    authorization.check_credential = AsyncMock(
        return_value=CredentialHealth(
            user_id="bot-b",
            token_type="bot",
            status="valid",
            last_checked_at=_NOW,
            last_validated_at=_NOW,
        )
    )

    response = _client(service, authorization=authorization).post(
        "/api/tenants/channel-a/bot-accounts/bot-b/authorization-check",
        headers={"X-Niibot-Action": "twitch-authorization-management"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "valid"
    authorization.check_credential.assert_awaited_once_with(
        user_id="bot-b", token_type="bot", required_scopes=set(BOT_CORE_SCOPES)
    )


def test_tenant_can_read_scope_safe_capability_snapshot():
    service = MagicMock()
    authorization = MagicMock()
    authorization.get_capability_snapshot = AsyncMock(
        return_value=TwitchCapabilitySnapshot(
            broadcaster_status="valid",
            bot_status="valid",
            bot_user_id="bot-test",
            capabilities=(
                CapabilityHealth(
                    key="broadcaster_chat",
                    label="頻道聊天",
                    credential="broadcaster",
                    available=True,
                    missing_scopes=(),
                    core=True,
                ),
                CapabilityHealth(
                    key="moderator_sync_realtime",
                    label="Twitch MOD 即時同步",
                    credential="broadcaster",
                    available=False,
                    missing_scopes=("moderation:read",),
                    core=False,
                ),
            ),
        )
    )

    response = _client(service, authorization=authorization).get(
        "/api/tenants/channel-a/twitch-capabilities"
    )

    assert response.status_code == 200
    assert response.json() == {
        "broadcaster_status": "valid",
        "bot_status": "valid",
        "bot_user_id": "bot-test",
        "capabilities": [
            {
                "key": "broadcaster_chat",
                "label": "頻道聊天",
                "credential": "broadcaster",
                "available": True,
                "missing_scopes": [],
                "core": True,
            },
            {
                "key": "moderator_sync_realtime",
                "label": "Twitch MOD 即時同步",
                "credential": "broadcaster",
                "available": False,
                "missing_scopes": ["moderation:read"],
                "core": False,
            },
        ],
    }
    authorization.get_capability_snapshot.assert_awaited_once_with(
        channel_id="channel-a", system_bot_id="bot-test"
    )


def test_owner_can_unlink_only_this_tenants_bot_mapping():
    service = MagicMock()
    authorization = MagicMock()
    authorization.unlink_bot_from_tenant = AsyncMock(
        return_value=AuthorizationRemovalResult(
            credential_retained=True,
            upstream_revoke_confirmed=False,
        )
    )

    response = _client(service, authorization=authorization).delete(
        "/api/tenants/channel-a/bot-accounts/bot-b",
        headers={"X-Niibot-Action": "twitch-authorization-management"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "credential_retained": True,
        "upstream_revoke_confirmed": False,
    }
    authorization.unlink_bot_from_tenant.assert_awaited_once_with(
        channel_id="channel-a", bot_user_id="bot-b", actor_user_id=_USER_ID
    )


def test_tenant_can_read_broadcaster_authorization_summary():
    service = MagicMock()
    authorization = MagicMock()
    authorization.get_broadcaster_summary = AsyncMock(
        return_value=BroadcasterAuthorizationSummary(
            channel_id="channel-a",
            channel_name="alice",
            display_name="Alice",
            enabled=True,
            status="valid",
            last_checked_at=_NOW,
            last_validated_at=_NOW,
            error_code=None,
        )
    )

    response = _client(service, authorization=authorization).get(
        "/api/tenants/channel-a/broadcaster-authorization"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "valid"
    assert response.json()["channel_name"] == "alice"


def test_owner_rechecks_broadcaster_against_runtime_core_only():
    service = MagicMock()
    authorization = MagicMock()
    authorization.check_credential = AsyncMock(
        return_value=CredentialHealth(
            user_id="channel-a",
            token_type="broadcaster",
            status="valid",
            last_checked_at=_NOW,
            last_validated_at=_NOW,
        )
    )

    response = _client(service, authorization=authorization).post(
        "/api/tenants/channel-a/broadcaster-authorization/check",
        headers={"X-Niibot-Action": "twitch-authorization-management"},
    )

    assert response.status_code == 200
    authorization.check_credential.assert_awaited_once_with(
        user_id="channel-a",
        token_type="broadcaster",
        required_scopes=set(BROADCASTER_CORE_SCOPES),
    )


def test_owner_disconnects_broadcaster_and_current_cookie_is_cleared():
    service = MagicMock()
    authorization = MagicMock()
    authorization.disconnect_broadcaster = AsyncMock(
        return_value=AuthorizationRemovalResult(
            credential_retained=False,
            upstream_revoke_confirmed=True,
        )
    )

    response = _client(service, authorization=authorization).delete(
        "/api/tenants/channel-a/broadcaster-authorization",
        headers={"X-Niibot-Action": "twitch-authorization-management"},
    )

    assert response.status_code == 200
    assert "auth_token=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
    authorization.disconnect_broadcaster.assert_awaited_once_with(
        channel_id="channel-a", owner_user_id=_USER_ID
    )
