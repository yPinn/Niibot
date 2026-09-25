"""API configuration security contracts."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from core.config import Settings

_TWITCH_KEY = Fernet.generate_key().decode()
_PAYMENT_KEY = Fernet.generate_key().decode()


def _settings(**overrides: str) -> Settings:
    values = {
        "database_url": "postgresql://user:pass@localhost/db",
        "environment": "staging",
        "twitch_token_encryption_key": _TWITCH_KEY,
        "client_id": "client-id",
        "client_secret": "client-secret",
        "jwt_secret_key": "jwt-secret",
        "payment_encryption_key": _PAYMENT_KEY,
    }
    values.update(overrides)
    return Settings(**values, _env_file=None)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_api_requires_payment_encryption_key(environment: str) -> None:
    with pytest.raises(ValidationError, match="PAYMENT_ENCRYPTION_KEY"):
        _settings(environment=environment, payment_encryption_key="")


def test_payment_encryption_key_must_be_valid_fernet() -> None:
    with pytest.raises(ValidationError, match="PAYMENT_ENCRYPTION_KEY"):
        _settings(payment_encryption_key="not-a-fernet-key")


def test_development_api_allows_payment_feature_to_remain_disabled() -> None:
    settings = _settings(environment="development", payment_encryption_key="")

    assert settings.payment_encryption_key == ""
