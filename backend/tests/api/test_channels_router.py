"""Tests for api.routers.channels_router — mod-status and grant-mod endpoints."""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("FRONTEND_URL", "https://niibot.tv")
os.environ.setdefault("BOT_ID", "bot-999")

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.channel_service as cs
from core.config import get_settings
from core.dependencies import (
    get_current_channel_id,
    get_db_pool,
    get_twitch_api,
    get_twitch_authorization_service,
    require_activated,
    require_tenant_access,
)
from core.error_handlers import register_exception_handlers
from routers.channels_router import router as _channels_router
from routers.channels_router import tenant_router as _tenant_channels_router
from services.tenant_service import TenantContext

CHANNEL_ID = "ch-123"


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _make_client(
    *,
    twitch_api: MagicMock | None = None,
    authorization: MagicMock | None = None,
) -> TestClient:
    """Build a TestClient with all heavyweight dependencies stubbed out."""
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_channels_router)

    mock_api = twitch_api or MagicMock()
    mock_authorization = authorization if authorization is not None else MagicMock()
    if authorization is None:
        mock_authorization.require_capability = AsyncMock()
    mock_pool = AsyncMock()

    app.dependency_overrides[get_current_channel_id] = lambda: CHANNEL_ID
    app.dependency_overrides[get_twitch_api] = lambda: mock_api
    app.dependency_overrides[get_twitch_authorization_service] = lambda: mock_authorization
    app.dependency_overrides[get_db_pool] = lambda: mock_pool
    app.dependency_overrides[require_activated] = lambda: None

    return TestClient(app, raise_server_exceptions=False)


def _make_tenant_client(
    *,
    twitch_api: MagicMock | None = None,
    channel_id: str = "workspace-789",
) -> TestClient:
    app = FastAPI(lifespan=_no_lifespan)
    register_exception_handlers(app)
    app.include_router(_tenant_channels_router)

    app.dependency_overrides[get_twitch_api] = lambda: twitch_api or MagicMock()
    app.dependency_overrides[get_db_pool] = lambda: AsyncMock()
    app.dependency_overrides[require_tenant_access] = lambda: TenantContext(
        channel_id=channel_id,
        user_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        role="manager",
    )
    return TestClient(app, raise_server_exceptions=False)


# ============================================
# GET /api/channels/twitch/mod-status
# ============================================


class TestGetBotModStatus:
    def test_returns_is_moderator_true(self):
        mock_api = MagicMock()
        mock_api.get_bot_mod_status = AsyncMock(return_value="mod")
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.get("/api/channels/twitch/mod-status")

        assert r.status_code == 200
        assert r.json() == {"is_moderator": True}

    def test_returns_is_moderator_false(self):
        mock_api = MagicMock()
        mock_api.get_bot_mod_status = AsyncMock(return_value="no_mod")
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.get("/api/channels/twitch/mod-status")

        assert r.status_code == 200
        assert r.json() == {"is_moderator": False}

    def test_returns_403_with_reauth_header_when_token_missing(self):
        client = _make_client()

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value=None)
        ):
            r = client.get("/api/channels/twitch/mod-status")

        assert r.status_code == 403
        assert r.headers.get("x-reauth-required") == "true"
        assert r.json()["error"]["code"] == "TWITCH_AUTH.CREDENTIAL_INVALID"

    def test_missing_optional_scope_is_local_feature_lock(self):
        authorization = MagicMock()
        from services.twitch_authorization_service import TwitchScopeRequiredError

        authorization.require_capability = AsyncMock(
            side_effect=TwitchScopeRequiredError(fields={"capability": "moderator_management"})
        )

        r = _make_client(authorization=authorization).get("/api/channels/twitch/mod-status")

        assert r.status_code == 403
        assert r.headers.get("x-reauth-required") is None
        assert r.json()["error"]["code"] == "TWITCH_AUTH.SCOPE_REQUIRED"

    def test_passes_bot_id_from_settings_to_api(self):
        mock_api = MagicMock()
        mock_api.get_bot_mod_status = AsyncMock(return_value="no_mod")
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            client.get("/api/channels/twitch/mod-status")

        expected_bot_id = get_settings().bot_id
        mock_api.get_bot_mod_status.assert_awaited_once_with(
            CHANNEL_ID, expected_bot_id, "valid-token"
        )


# ============================================
# POST /api/channels/twitch/grant-mod
# ============================================


class TestGrantBotMod:
    def _helix_response(self, status_code: int, body: str = "") -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.text = body
        return resp

    def test_204_returns_granted_true(self):
        mock_api = MagicMock()
        mock_api.add_moderator = AsyncMock(return_value=self._helix_response(204))
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.post("/api/channels/twitch/grant-mod")

        assert r.status_code == 200
        assert r.json() == {"granted": True, "already_mod": False}

    def test_422_returns_already_mod(self):
        mock_api = MagicMock()
        mock_api.add_moderator = AsyncMock(return_value=self._helix_response(422))
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.post("/api/channels/twitch/grant-mod")

        assert r.status_code == 200
        assert r.json() == {"granted": False, "already_mod": True}

    def test_401_from_helix_returns_403_with_reauth_header(self):
        mock_api = MagicMock()
        mock_api.add_moderator = AsyncMock(return_value=self._helix_response(401))
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.post("/api/channels/twitch/grant-mod")

        assert r.status_code == 403
        assert r.headers.get("x-reauth-required") == "true"
        assert r.json()["error"]["code"] == "TWITCH_AUTH.CREDENTIAL_INVALID"

    def test_403_from_helix_is_scope_lock_without_reauth_header(self):
        mock_api = MagicMock()
        mock_api.add_moderator = AsyncMock(return_value=self._helix_response(403))
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.post("/api/channels/twitch/grant-mod")

        assert r.status_code == 403
        assert r.headers.get("x-reauth-required") is None
        assert r.json()["error"]["code"] == "TWITCH_AUTH.SCOPE_REQUIRED"

    def test_missing_token_returns_403_with_reauth_header(self):
        client = _make_client()

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value=None)
        ):
            r = client.post("/api/channels/twitch/grant-mod")

        assert r.status_code == 403
        assert r.headers.get("x-reauth-required") == "true"
        assert r.json()["error"]["code"] == "TWITCH_AUTH.CREDENTIAL_INVALID"

    def test_add_moderator_exception_returns_provider_unavailable(self):
        mock_api = MagicMock()
        mock_api.add_moderator = AsyncMock(side_effect=Exception("network failure"))
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.post("/api/channels/twitch/grant-mod")

        assert r.status_code == 503
        assert r.json()["error"]["code"] == "TWITCH_AUTH.PROVIDER_UNAVAILABLE"

    def test_unexpected_helix_status_returns_502(self):
        mock_api = MagicMock()
        mock_api.add_moderator = AsyncMock(return_value=self._helix_response(500, "server error"))
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            r = client.post("/api/channels/twitch/grant-mod")

        assert r.status_code == 503
        assert r.json()["error"]["code"] == "TWITCH_AUTH.PROVIDER_UNAVAILABLE"

    def test_passes_bot_id_and_channel_id_to_api(self):
        mock_api = MagicMock()
        mock_api.add_moderator = AsyncMock(return_value=self._helix_response(204))
        client = _make_client(twitch_api=mock_api)

        with patch.object(
            cs.ChannelService, "get_token_with_refresh", AsyncMock(return_value="valid-token")
        ):
            client.post("/api/channels/twitch/grant-mod")

        expected_bot_id = get_settings().bot_id
        mock_api.add_moderator.assert_awaited_once_with(CHANNEL_ID, expected_bot_id, "valid-token")


# ============================================
# GET /api/channels/emotes
# ============================================


def _make_emote(eid: str, name: str, etype: str = "globals") -> dict:
    return {
        "id": eid,
        "name": name,
        "url": f"https://cdn.example.com/{eid}.png",
        "emote_type": etype,
        "tier": "",
        "animated": False,
    }


class TestGetChannelEmotes:
    def test_returns_global_and_channel_emotes_without_bot_token(self):
        mock_twitch = MagicMock()
        mock_twitch.get_global_emotes = AsyncMock(return_value=[_make_emote("g1", "PogChamp")])
        mock_twitch.get_channel_emotes = AsyncMock(
            return_value=[_make_emote("c1", "Kappa", "subscriptions")]
        )

        with (
            patch("routers.channels_router.ChannelRepository") as cr,
            patch("routers.channels_router.resolve_bot_id", AsyncMock(return_value="bot-999")),
            patch("routers.channels_router.sync_enabled_emotes_background", AsyncMock()),
        ):
            cr.return_value.get_token = AsyncMock(return_value=None)
            r = _make_client(twitch_api=mock_twitch).get("/api/channels/emotes")

        assert r.status_code == 200
        body = r.json()
        assert body["bot_user_id"] == "bot-999"
        assert body["bot_token_available"] is False
        names = {e["name"] for e in body["emotes"]}
        assert "PogChamp" in names
        assert "Kappa" in names

    def test_globals_and_follower_emotes_are_always_available(self):
        mock_twitch = MagicMock()
        mock_twitch.get_global_emotes = AsyncMock(return_value=[_make_emote("g1", "PogChamp")])
        mock_twitch.get_channel_emotes = AsyncMock(
            return_value=[_make_emote("f1", "FollowEmote", "follower")]
        )

        with (
            patch("routers.channels_router.ChannelRepository") as cr,
            patch("routers.channels_router.resolve_bot_id", AsyncMock(return_value="bot-999")),
            patch("routers.channels_router.sync_enabled_emotes_background", AsyncMock()),
        ):
            cr.return_value.get_token = AsyncMock(return_value=None)
            r = _make_client(twitch_api=mock_twitch).get("/api/channels/emotes")

        emotes = {e["name"]: e for e in r.json()["emotes"]}
        assert emotes["PogChamp"]["available"] is True
        assert emotes["FollowEmote"]["available"] is True

    def test_sub_emote_available_when_bot_has_access(self):
        mock_twitch = MagicMock()
        mock_twitch.get_global_emotes = AsyncMock(return_value=[])
        mock_twitch.get_channel_emotes = AsyncMock(
            return_value=[_make_emote("s1", "SubEmote", "subscriptions")]
        )
        mock_twitch.get_user_emotes = AsyncMock(
            return_value=[_make_emote("s1", "SubEmote", "subscriptions")]
        )

        token_row = MagicMock()
        token_row.token = "bot-token"

        with (
            patch("routers.channels_router.ChannelRepository") as cr,
            patch("routers.channels_router.resolve_bot_id", AsyncMock(return_value="bot-999")),
            patch("routers.channels_router.sync_enabled_emotes_background", AsyncMock()),
        ):
            cr.return_value.get_token = AsyncMock(return_value=token_row)
            r = _make_client(twitch_api=mock_twitch).get("/api/channels/emotes")

        body = r.json()
        assert body["bot_token_available"] is True
        emotes = {e["name"]: e for e in body["emotes"]}
        assert emotes["SubEmote"]["available"] is True

    def test_surfaces_emotes_unlocked_on_other_channels(self):
        """The bot account's subscription emote from a channel it doesn't even
        speak in must still come back, grouped under that channel — those
        emotes are usable in ANY chat once unlocked."""
        mock_twitch = MagicMock()
        mock_twitch.get_global_emotes = AsyncMock(return_value=[])
        mock_twitch.get_channel_emotes = AsyncMock(return_value=[])
        mock_twitch.get_user_emotes = AsyncMock(
            return_value=[
                {**_make_emote("e1", "OtherSub", "subscriptions"), "owner_id": "other-channel"}
            ]
        )
        mock_twitch.get_users_by_ids = AsyncMock(
            return_value=[
                {
                    "id": "other-channel",
                    "login": "otherchannel",
                    "display_name": "OtherChannel",
                    "profile_image_url": "https://img/other.png",
                }
            ]
        )

        token_row = MagicMock()
        token_row.token = "bot-token"

        with (
            patch("routers.channels_router.ChannelRepository") as cr,
            patch("routers.channels_router.resolve_bot_id", AsyncMock(return_value="bot-999")),
            patch("routers.channels_router.sync_enabled_emotes_background", AsyncMock()),
        ):
            cr.return_value.get_token = AsyncMock(return_value=token_row)
            r = _make_client(twitch_api=mock_twitch).get("/api/channels/emotes")

        body = r.json()
        assert not body["emotes"]
        [group] = body["other_channels"]
        assert group["channel_id"] == "other-channel"
        assert group["channel_name"] == "otherchannel"
        assert group["emotes"][0]["name"] == "OtherSub"

    def test_exception_returns_500(self):
        mock_twitch = MagicMock()
        mock_twitch.get_global_emotes = AsyncMock(side_effect=RuntimeError("api error"))
        mock_twitch.get_channel_emotes = AsyncMock(return_value=[])

        with (
            patch("routers.channels_router.ChannelRepository") as cr,
            patch("routers.channels_router.resolve_bot_id", AsyncMock(return_value="bot-999")),
        ):
            cr.return_value.get_token = AsyncMock(return_value=None)
            r = _make_client(twitch_api=mock_twitch).get("/api/channels/emotes")

        assert r.status_code == 500

    def test_tenant_route_uses_authorized_workspace_for_emotes(self):
        workspace_id = "workspace-789"
        mock_twitch = MagicMock()
        mock_twitch.get_global_emotes = AsyncMock(return_value=[])
        mock_twitch.get_channel_emotes = AsyncMock(return_value=[])

        with (
            patch("routers.channels_router.ChannelRepository") as cr,
            patch("routers.channels_router.resolve_bot_id", AsyncMock(return_value="bot-999")),
            patch("routers.channels_router.sync_enabled_emotes_background", AsyncMock()),
        ):
            cr.return_value.get_token = AsyncMock(return_value=None)
            response = _make_tenant_client(
                twitch_api=mock_twitch,
                channel_id=workspace_id,
            ).get(f"/api/tenants/{workspace_id}/emotes")

        assert response.status_code == 200
        mock_twitch.get_channel_emotes.assert_awaited_once_with(workspace_id)
