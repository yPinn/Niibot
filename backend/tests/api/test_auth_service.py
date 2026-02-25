"""Unit tests for api.services.auth_service.AuthService."""

# conftest.py adds backend/ to sys.path — use full package path from there
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from api.services.auth_service import AuthService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def service() -> AuthService:
    return AuthService(secret_key="test-secret-key-for-unit-tests-32b")


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestAuthServiceInit:
    def test_empty_secret_raises_value_error(self):
        with pytest.raises(ValueError):
            AuthService(secret_key="")

    def test_valid_secret_creates_instance(self):
        svc = AuthService(secret_key="valid-secret")
        assert svc is not None


# ---------------------------------------------------------------------------
# create_access_token
# ---------------------------------------------------------------------------


class TestCreateAccessToken:
    def test_returns_non_empty_string(self, service: AuthService):
        token = service.create_access_token("user-1", "twitch", "12345")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_expected_claims(self, service: AuthService):
        token = service.create_access_token("user-1", "twitch", "54321")
        payload = jwt.decode(token, "test-secret-key-for-unit-tests-32b", algorithms=["HS256"])
        assert payload["sub"] == "user-1"
        assert payload["platform"] == "twitch"
        assert payload["platform_user_id"] == "54321"

    def test_token_has_expiry(self, service: AuthService):
        token = service.create_access_token("u", "twitch", "1")
        payload = jwt.decode(token, "test-secret-key-for-unit-tests-32b", algorithms=["HS256"])
        assert "exp" in payload

    def test_token_has_issued_at(self, service: AuthService):
        token = service.create_access_token("u", "twitch", "1")
        payload = jwt.decode(token, "test-secret-key-for-unit-tests-32b", algorithms=["HS256"])
        assert "iat" in payload


# ---------------------------------------------------------------------------
# verify_token — valid tokens
# ---------------------------------------------------------------------------


class TestVerifyTokenValid:
    def test_verify_returns_payload_for_valid_token(self, service: AuthService):
        token = service.create_access_token("user-1", "twitch", "999")
        payload = service.verify_token(token)
        assert payload is not None
        assert payload["sub"] == "user-1"
        assert payload["platform_user_id"] == "999"

    def test_verify_round_trip(self, service: AuthService):
        token = service.create_access_token("abc", "discord", "xyz")
        payload = service.verify_token(token)
        assert payload["sub"] == "abc"
        assert payload["platform"] == "discord"
        assert payload["platform_user_id"] == "xyz"


# ---------------------------------------------------------------------------
# verify_token — invalid / tampered tokens
# ---------------------------------------------------------------------------


class TestVerifyTokenInvalid:
    def test_returns_none_for_garbage_string(self, service: AuthService):
        assert service.verify_token("not.a.jwt.at.all") is None

    def test_returns_none_for_wrong_secret(self, service: AuthService):
        other = AuthService(secret_key="completely-different-secret")
        token = other.create_access_token("u", "twitch", "1")
        assert service.verify_token(token) is None

    def test_returns_none_for_tampered_signature(self, service: AuthService):
        token = service.create_access_token("u", "twitch", "1")
        tampered = token[:-8] + "XXXXXXXX"
        assert service.verify_token(tampered) is None

    def test_returns_none_for_expired_token(self):
        svc = AuthService(secret_key="test-secret-key-for-unit-tests-32b", expire_days=-1)
        token = svc.create_access_token("u", "twitch", "1")
        assert svc.verify_token(token) is None

    def test_returns_none_for_token_missing_sub(self, service: AuthService):
        payload = {
            "platform": "twitch",
            "platform_user_id": "1",
            "exp": datetime.now(UTC) + timedelta(days=1),
            "iat": datetime.now(UTC),
        }
        token = jwt.encode(payload, "test-secret-key-for-unit-tests-32b", algorithm="HS256")
        assert service.verify_token(token) is None

    def test_returns_none_for_empty_string(self, service: AuthService):
        assert service.verify_token("") is None
