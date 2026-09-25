"""Contracts for versioned Twitch credential encryption."""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from shared import config_base
from shared.config_base import BaseServiceSettings
from shared.twitch_token_crypto import (
    CURRENT_TWITCH_TOKEN_ENCRYPTION_VERSION,
    TwitchTokenEncryptionError,
    decrypt_twitch_token,
    encrypt_twitch_token,
)

_KEY = Fernet.generate_key().decode()


def test_v1_roundtrip_uses_explicit_envelope():
    ciphertext, version = encrypt_twitch_token("oauth:secret", _KEY)

    assert version == CURRENT_TWITCH_TOKEN_ENCRYPTION_VERSION == 1
    assert ciphertext.startswith("v1:")
    assert "oauth:secret" not in ciphertext
    assert decrypt_twitch_token(ciphertext, version=version, key=_KEY) == "oauth:secret"


def test_legacy_plaintext_is_only_accepted_when_row_is_explicitly_version_zero():
    assert decrypt_twitch_token("legacy-secret", version=0, key=None) == "legacy-secret"

    with pytest.raises(TwitchTokenEncryptionError, match="envelope"):
        decrypt_twitch_token("legacy-secret", version=1, key=_KEY)


def test_encrypted_row_requires_a_configured_key():
    ciphertext, version = encrypt_twitch_token("secret", _KEY)

    with pytest.raises(TwitchTokenEncryptionError, match="not configured"):
        decrypt_twitch_token(ciphertext, version=version, key=None)


def test_wrong_key_or_tampered_value_fails_closed():
    ciphertext, version = encrypt_twitch_token("secret", _KEY)

    with pytest.raises(TwitchTokenEncryptionError, match="could not be decrypted"):
        decrypt_twitch_token(ciphertext, version=version, key=Fernet.generate_key().decode())


@pytest.mark.parametrize("version", [-1, 2, 99])
def test_unknown_encryption_versions_fail_closed(version: int):
    with pytest.raises(TwitchTokenEncryptionError, match="Unsupported"):
        decrypt_twitch_token("anything", version=version, key=_KEY)


def test_production_configuration_requires_twitch_token_encryption_key():
    with pytest.raises(ValidationError, match="TWITCH_TOKEN_ENCRYPTION_KEY"):
        BaseServiceSettings(
            database_url="postgresql://user:pass@localhost/db",
            environment="production",
            twitch_token_encryption_key="",
            _env_file=None,
        )


def test_staging_configuration_requires_twitch_token_encryption_key():
    with pytest.raises(ValidationError, match="TWITCH_TOKEN_ENCRYPTION_KEY"):
        BaseServiceSettings(
            database_url="postgresql://user:pass@localhost/db",
            environment="staging",
            twitch_token_encryption_key="",
            _env_file=None,
        )


def test_development_configuration_allows_bounded_plaintext_backfill_window():
    settings = BaseServiceSettings(
        database_url="postgresql://user:pass@localhost/db",
        environment="development",
        twitch_token_encryption_key="",
        _env_file=None,
    )

    assert settings.twitch_token_encryption_key == ""


@pytest.mark.parametrize("environment", ["dev", "stg", "prod", "testing"])
def test_runtime_environment_rejects_selectors_and_unknown_values(environment: str):
    with pytest.raises(ValidationError, match="ENVIRONMENT"):
        BaseServiceSettings(
            database_url="postgresql://user:pass@localhost/db",
            environment=environment,
            _env_file=None,
        )


def test_dev_env_loader_keeps_process_values_and_applies_local_precedence(tmp_path, monkeypatch):
    shared = tmp_path / "shared.env"
    local = tmp_path / "local.env"
    shared.write_text("FROM_FILE=shared\nOVERRIDE=file\n", encoding="utf-8")
    local.write_text("FROM_FILE=local\nLOCAL_ONLY=yes\n", encoding="utf-8")
    monkeypatch.setattr(config_base, "dev_env_files", lambda _service: (shared, local))
    monkeypatch.setenv("OVERRIDE", "process")

    config_base.load_dev_env("api")

    assert os.environ["FROM_FILE"] == "local"
    assert os.environ["LOCAL_ONLY"] == "yes"
    assert os.environ["OVERRIDE"] == "process"


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_deployed_runtime_does_not_consider_dev_env_files(environment: str, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.delenv("NIIBOT_RUNTIME_CONTEXT", raising=False)

    assert config_base.dev_env_files("api") == ()


def test_container_runtime_does_not_consider_dev_env_files(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("NIIBOT_RUNTIME_CONTEXT", "container")

    assert config_base.dev_env_files("twitch") == ()
