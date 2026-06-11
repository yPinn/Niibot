"""Integration tests for api.routers.auth_router.

Each test class spins up a minimal FastAPI app that includes only the auth
router. External dependencies (DB pool, Twitch API) are mocked so tests run
without any network or database connection.
"""

# ruff: noqa: E402  — env vars must be set before Settings-using imports
from __future__ import annotations

# ---------------------------------------------------------------------------
# Set test env vars BEFORE any Settings-using imports
# ---------------------------------------------------------------------------
import os

_JWT_SECRET = "test-jwt-secret-key-for-auth-router-tests"  # 43 bytes

os.environ.setdefault("JWT_SECRET_KEY", _JWT_SECRET)
os.environ.setdefault("CLIENT_ID", "test-client-id")
os.environ.setdefault("CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.config import get_settings
from core.dependencies import (
    get_auth_service,
    get_current_user_id,
    get_db_pool,
    get_twitch_api,
)
from routers.auth_router import router as _auth_router
from services.auth_service import AuthService

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_USER_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
_TWITCH_UID = "12345678"
_AUTH = AuthService(secret_key=_JWT_SECRET)


def _token(
    user_id: str = _USER_UUID,
    platform: str = "twitch",
    platform_user_id: str = _TWITCH_UID,
) -> str:
    return _AUTH.create_access_token(user_id, platform, platform_user_id)


# ---------------------------------------------------------------------------
# App / mock helpers
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _no_lifespan(app: FastAPI):
    yield


def _make_pool(
    *,
    fetchrow=None,
    fetch=None,
    fetchval=None,
    execute: str = "UPDATE 0",
) -> AsyncMock:
    """Pool mock that handles both direct calls and the acquire() pattern."""
    pool = AsyncMock()
    pool.fetchrow.return_value = fetchrow
    pool.fetch.return_value = fetch if fetch is not None else []
    pool.fetchval.return_value = fetchval
    pool.execute.return_value = execute

    # asyncpg pool.acquire() is synchronous — returns a context manager, not a coroutine.
    # Override with MagicMock so that async with pool.acquire() as conn works correctly.
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    acquire_ctx = MagicMock()
    acquire_ctx.__aenter__ = AsyncMock(return_value=conn)
    acquire_ctx.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=acquire_ctx)
    return pool


def _make_twitch_api(user_info: dict | None = None) -> MagicMock:
    api = MagicMock()
    api.generate_oauth_url.return_value = "https://id.twitch.tv/oauth2/authorize?test=1"
    api.get_user_info = AsyncMock(
        return_value=user_info
        or {
            "id": _TWITCH_UID,
            "name": "testuser",
            "display_name": "Test User",
            "avatar": "https://cdn.test/avatar.png",
        }
    )
    return api


def _make_client(
    pool: AsyncMock | None = None,
    twitch_api: MagicMock | None = None,
    *,
    override_user_id: bool = False,
) -> TestClient:
    """Build a TestClient with mocked external dependencies."""
    app = FastAPI(lifespan=_no_lifespan)
    app.include_router(_auth_router)

    _pool = pool or _make_pool()
    app.dependency_overrides[get_auth_service] = lambda: _AUTH
    app.dependency_overrides[get_db_pool] = lambda: _pool
    app.dependency_overrides[get_twitch_api] = lambda: twitch_api or _make_twitch_api()

    if override_user_id:

        async def _fixed_uid() -> str:
            return _USER_UUID

        app.dependency_overrides[get_current_user_id] = _fixed_uid

    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    """Re-create Settings from env vars for each test (clears LRU cache)."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _clear_channel_caches():
    """Prevent cache pollution from ChannelRepository between tests."""
    from shared.repositories.channel import (
        _channel_cache,
        _discord_user_cache,
        _enabled_channels_cache,
        _token_cache,
    )

    for cache in (_discord_user_cache, _channel_cache, _enabled_channels_cache, _token_cache):
        cache.clear()
        cache._stale.clear()
    yield


# ---------------------------------------------------------------------------
# GET /api/auth/user
# ---------------------------------------------------------------------------


class TestGetCurrentUser:
    def test_no_cookie_returns_401(self):
        r = _make_client().get("/api/auth/user")
        assert r.status_code == 401

    def test_invalid_token_returns_401(self):
        client = _make_client()
        client.cookies.set("auth_token", "not.a.valid.jwt")
        r = client.get("/api/auth/user")
        assert r.status_code == 401

    def test_valid_twitch_token_returns_user_info(self):
        pool = _make_pool(fetchrow={"theme": "dark"})
        client = _make_client(pool=pool)
        client.cookies.set("auth_token", _token())
        r = client.get("/api/auth/user")

        assert r.status_code == 200
        data = r.json()
        assert data["platform"] == "twitch"
        assert data["name"] == "testuser"
        assert data["theme"] == "dark"

    def test_theme_defaults_to_system_when_no_user_row(self):
        pool = _make_pool(fetchrow=None)
        client = _make_client(pool=pool)
        client.cookies.set("auth_token", _token())
        r = client.get("/api/auth/user")

        assert r.status_code == 200
        assert r.json()["theme"] == "system"

    def test_twitch_user_not_found_returns_404(self):
        pool = _make_pool(fetchrow=None)
        twitch_api = _make_twitch_api()
        twitch_api.get_user_info = AsyncMock(return_value=None)
        client = _make_client(pool=pool, twitch_api=twitch_api)
        client.cookies.set("auth_token", _token())
        r = client.get("/api/auth/user")

        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/auth/logout
# ---------------------------------------------------------------------------


class TestLogout:
    def test_no_cookie_returns_401(self):
        r = _make_client().post("/api/auth/logout")
        assert r.status_code == 401

    def test_valid_twitch_token_returns_200(self):
        client = _make_client()
        client.cookies.set("auth_token", _token())
        r = client.post("/api/auth/logout")

        assert r.status_code == 200
        assert r.json()["message"] == "Logged out successfully"

    def test_logout_clears_auth_cookie(self):
        client = _make_client()
        client.cookies.set("auth_token", _token())
        r = client.post("/api/auth/logout")

        set_cookie = r.headers.get("set-cookie", "")
        assert "auth_token" in set_cookie


# ---------------------------------------------------------------------------
# GET /api/auth/twitch/oauth
# ---------------------------------------------------------------------------


class TestTwitchOAuthUrl:
    def test_login_mode_returns_oauth_url(self):
        r = _make_client().get("/api/auth/twitch/oauth")

        assert r.status_code == 200
        data = r.json()
        assert "oauth_url" in data
        assert "redirect_uri" in data
        assert "twitch" in data["oauth_url"]


# ---------------------------------------------------------------------------
# GET /api/auth/twitch/callback — CSRF / state validation
# ---------------------------------------------------------------------------


class TestTwitchOAuthCallback:
    """Callback security: state must be present and HMAC-verified before code exchange."""

    def test_oauth_error_param_redirects_to_login(self):
        """When Twitch sends ?error=access_denied the callback must redirect to /login."""
        client = _make_client()
        r = client.get(
            "/api/auth/twitch/callback",
            params={"error": "access_denied"},
            follow_redirects=False,
        )
        assert r.status_code in (302, 307)
        assert "/login" in r.headers["location"]
        assert "access_denied" in r.headers["location"]

    def test_missing_state_redirects_with_invalid_state_error(self):
        """No state parameter must be rejected — not silently treated as login."""
        client = _make_client()
        r = client.get(
            "/api/auth/twitch/callback",
            params={"code": "somecode"},
            follow_redirects=False,
        )
        assert r.status_code in (302, 307)
        location = r.headers["location"]
        assert "/login" in location
        assert "invalid_state" in location

    def test_tampered_state_redirects_with_invalid_state_error(self):
        """Tampered state must be rejected before the code is exchanged."""
        client = _make_client()
        r = client.get(
            "/api/auth/twitch/callback",
            params={"code": "somecode", "state": "dGhpcyBpcyBub3QgdmFsaWQ"},
            follow_redirects=False,
        )
        assert r.status_code in (302, 307)
        location = r.headers["location"]
        assert "/login" in location
        assert "invalid_state" in location

    def test_db_not_ready_redirects_with_error(self):
        """If the DB manager raises RuntimeError the callback must redirect gracefully."""
        from services.oauth_service import encode_oauth_state

        settings = get_settings()
        valid_state = encode_oauth_state("login", secret=settings.jwt_secret_key)

        client = _make_client()
        with patch("routers.auth_router.get_database_manager") as mock_dbm:
            mock_dbm.side_effect = RuntimeError("pool not ready")
            r = client.get(
                "/api/auth/twitch/callback",
                params={"code": "somecode", "state": valid_state},
                follow_redirects=False,
            )
        assert r.status_code in (302, 307)
        assert "db_not_ready" in r.headers["location"]


# ---------------------------------------------------------------------------
# GET /api/auth/twitch/callback — successful flow with scopes
# ---------------------------------------------------------------------------


class TestTwitchOAuthCallbackSuccess:
    """Happy-path: verifies the OAuth callback's 4-stage pipeline.

    Stages exercised:
      1. ChannelService.save_token  — credential persistence
      2. IdentityService.find_or_link — identity binding
      3. AdmissionService.ensure_pending / auto_admit — admission state
      4. TenantService.ensure_tenant_for_owner — tenant bootstrap
    """

    def _run(
        self,
        scopes_value,
        *,
        is_new_user: bool = False,
        was_reconciled: bool = False,
        twitch_uid: str = _TWITCH_UID,
    ):
        from services.oauth_service import encode_oauth_state

        settings = get_settings()
        valid_state = encode_oauth_state("login", secret=settings.jwt_secret_key)

        twitch_api = _make_twitch_api()
        twitch_api.exchange_code_for_token = AsyncMock(
            return_value=(
                True,
                None,
                {
                    "access_token": "acc_tok",
                    "refresh_token": "ref_tok",
                    "user_id": twitch_uid,
                    "scopes": scopes_value,
                },
            )
        )

        pool = _make_pool()
        mock_channel_svc = MagicMock()
        mock_channel_svc.save_token = AsyncMock(return_value=True)

        # IdentityService mock — find_or_link returns a result describing the
        # branch taken (fast / link / reconciled / fresh).
        mock_identity = MagicMock()
        mock_identity.id = "11111111-2222-3333-4444-555555555555"
        mock_link_result = MagicMock(
            identity=mock_identity,
            user_id=_USER_UUID,
            is_new_user=is_new_user,
            is_new_identity=is_new_user or was_reconciled,
            was_reconciled=was_reconciled,
        )
        mock_identity_svc = MagicMock()
        mock_identity_svc.find_or_link = AsyncMock(return_value=mock_link_result)

        # AdmissionService mock — track whether each entry point fires so we
        # can assert reauth idempotency (the headline bug).
        mock_admission_svc = MagicMock()
        mock_admission_svc.ensure_pending = AsyncMock()
        mock_admission_svc.auto_admit = AsyncMock()

        # TenantService mock — bootstrap is unconditional and idempotent.
        mock_tenant_svc = MagicMock()
        mock_tenant_svc.ensure_tenant_for_owner = AsyncMock()

        with (
            patch("routers.auth_router.get_database_manager") as mock_dbm,
            patch("routers.auth_router.get_channel_service", return_value=mock_channel_svc),
            patch("routers.auth_router.IdentityService", return_value=mock_identity_svc),
            patch("routers.auth_router.AdmissionService", return_value=mock_admission_svc),
            patch("routers.auth_router.TenantService", return_value=mock_tenant_svc),
        ):
            mock_dbm.return_value.pool = pool
            client = _make_client(twitch_api=twitch_api)
            r = client.get(
                "/api/auth/twitch/callback",
                params={"code": "validcode", "state": valid_state},
                follow_redirects=False,
            )

        return r, mock_channel_svc, mock_identity_svc, mock_admission_svc, mock_tenant_svc

    def test_redirects_to_dashboard_on_success(self):
        r, *_ = self._run(scopes_value="channel:bot channel:read:redemptions")
        assert r.status_code in (302, 307)
        assert "/dashboard" in r.headers["location"]

    def test_scopes_forwarded_to_save_token(self):
        _, mock_channel_svc, *_ = self._run(scopes_value="channel:bot channel:read:redemptions")
        mock_channel_svc.save_token.assert_awaited_once()
        _, kwargs = mock_channel_svc.save_token.call_args
        assert kwargs.get("scopes") == "channel:bot channel:read:redemptions"

    def test_none_scopes_forwarded_as_none(self):
        _, mock_channel_svc, *_ = self._run(scopes_value=None)
        _, kwargs = mock_channel_svc.save_token.call_args
        assert kwargs.get("scopes") is None

    def test_reauth_does_not_touch_admission(self):
        """Regression test for the ghost-pending-request bug.

        Existing user reauthing must NOT trigger ensure_pending or
        auto_admit. IdentityService returns is_new_user=False; admission
        service should be left alone.
        """
        _, _, mock_identity, mock_admission, _ = self._run(
            scopes_value="channel:bot",
            is_new_user=False,
        )
        mock_identity.find_or_link.assert_awaited_once()
        mock_admission.ensure_pending.assert_not_awaited()
        mock_admission.auto_admit.assert_not_awaited()

    def test_new_user_signup_triggers_ensure_pending(self):
        """First-time signup should queue an admission request."""
        _, _, _, mock_admission, _ = self._run(
            scopes_value="channel:bot",
            is_new_user=True,
        )
        mock_admission.ensure_pending.assert_awaited_once()
        # ensure_pending receives user_id positionally
        args, kwargs = mock_admission.ensure_pending.call_args
        assert args[0] == _USER_UUID
        assert kwargs.get("reason") == "first_signup"

    def test_owner_signup_triggers_auto_admit(self):
        """Owner ID match should bypass admin review via auto_admit('owner')."""
        owner_id = str(get_settings().owner_id)
        _, _, _, mock_admission, _ = self._run(
            scopes_value="channel:bot",
            is_new_user=True,
            twitch_uid=owner_id,
        )
        # auto_admit fires, ensure_pending does NOT (auto_admit wins the
        # is_owner branch)
        mock_admission.auto_admit.assert_awaited_once()
        _, kwargs = mock_admission.auto_admit.call_args
        assert kwargs.get("reason") == "owner"
        mock_admission.ensure_pending.assert_not_awaited()

    def test_tenant_bootstrap_always_runs(self):
        """ensure_tenant_for_owner is idempotent and called on every callback."""
        _, _, _, _, mock_tenant = self._run(
            scopes_value="channel:bot",
            is_new_user=False,
        )
        mock_tenant.ensure_tenant_for_owner.assert_awaited_once()
        _, kwargs = mock_tenant.ensure_tenant_for_owner.call_args
        assert kwargs.get("channel_id") == _TWITCH_UID
        assert kwargs.get("owner_user_id") == _USER_UUID


# ---------------------------------------------------------------------------
# PATCH /api/user/preferences
# ---------------------------------------------------------------------------


class TestUpdatePreferences:
    def test_no_cookie_returns_401(self):
        r = _make_client().patch("/api/user/preferences", json={"theme": "dark"})
        assert r.status_code == 401

    def test_invalid_theme_returns_422(self):
        client = _make_client(override_user_id=True)
        client.cookies.set("auth_token", _token())
        r = client.patch(
            "/api/user/preferences",
            json={"theme": "rainbow"},
        )
        assert r.status_code == 422  # Pydantic Literal validation

    @pytest.mark.parametrize("theme", ["dark", "light", "system"])
    def test_valid_theme_returns_200(self, theme: str):
        pool = _make_pool(execute="UPDATE 1")
        client = _make_client(pool=pool, override_user_id=True)
        client.cookies.set("auth_token", _token())
        r = client.patch(
            "/api/user/preferences",
            json={"theme": theme},
        )
        assert r.status_code == 200
        assert r.json()["theme"] == theme


# ---------------------------------------------------------------------------
# POST /api/auth/activate — OTP rate limit
# ---------------------------------------------------------------------------


class TestActivateRateLimit:
    def test_rate_limit_exceeded_returns_429(self):
        """_otp_rate_limiter.allow() returning False must produce 429 too_many_attempts."""
        from routers.auth_router import _otp_rate_limiter

        pool = _make_pool(fetchval=None)  # fetchval=None → not yet activated
        client = _make_client(pool=pool)
        client.cookies.set("auth_token", _token())

        with patch.object(_otp_rate_limiter, "allow", return_value=False):
            r = client.post("/api/auth/activate", json={"code": "123456"})

        assert r.status_code == 429
        assert r.json()["detail"] == "too_many_attempts"
