"""Shared base settings for all Niibot services."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import dotenv_values
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings

LOGGER: logging.Logger = logging.getLogger(__name__)

# Shared paths keep service configs aligned in local and container runtimes.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = _BACKEND_DIR / "data"  # static repo content baked into image
RUNTIME_DIR = _BACKEND_DIR / "runtime"  # mutable state, volume-mounted per env


def dev_env_files(service: str) -> tuple[Path, ...]:
    """Local-dev env order; deployed containers inject their env directly."""
    runtime = os.getenv("ENVIRONMENT", "").lower()
    if os.getenv("NIIBOT_RUNTIME_CONTEXT") == "container" or runtime in {
        "staging",
        "production",
    }:
        return ()
    service_dir = _BACKEND_DIR / service
    return (
        _BACKEND_DIR / "shared.dev.env",
        _BACKEND_DIR / "shared.dev.local.env",
        service_dir / ".env.dev",
        service_dir / ".env.dev.local",
    )


def load_dev_env(service: str) -> None:
    """Merge dev files while preserving injected process values."""
    merged: dict[str, str | None] = {}
    for path in dev_env_files(service):
        merged.update(dotenv_values(path, encoding="utf-8"))
    for key, value in merged.items():
        if value is not None:
            os.environ.setdefault(key, value)


try:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # Writers surface a clearer error if the runtime filesystem is read-only.
    LOGGER.warning("Could not pre-create RUNTIME_DIR %s", RUNTIME_DIR, exc_info=True)


class BaseServiceSettings(BaseSettings):
    """Common settings shared across api, discord, and twitch services.

    Each subclass defines its local-dev env files; containers use process env.
    """

    # Database
    database_url: str = Field(..., description="PostgreSQL database URL")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    # Environment
    environment: str = Field(default="development", description="Runtime environment name")

    # Error reporting
    error_webhook_url: str = Field(default="", description="Discord webhook URL for error alerts")

    # Twitch credentials are shared by API OAuth callbacks and the Twitch runtime.
    twitch_token_encryption_key: str = Field(
        default="",
        description="Fernet key for versioned Twitch OAuth token encryption at rest",
    )

    # Shared by Discord previews and Video Queue Instagram support.
    instafix_host: str = Field(
        default="instafix:3000",
        description="InstaFix host (Docker: instafix:3000, local: localhost:3002)",
    )

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v.startswith("postgresql://"):
            raise ValueError("DATABASE_URL must start with 'postgresql://'")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            LOGGER.warning("Invalid log level %r, defaulting to INFO", v)
            return "INFO"
        return v_upper

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        value = v.lower()
        allowed = {"development", "staging", "production"}
        if value not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {sorted(allowed)}")
        return value

    @field_validator("twitch_token_encryption_key")
    @classmethod
    def validate_twitch_token_encryption_key(cls, v: str) -> str:
        if not v:
            return v
        try:
            from cryptography.fernet import Fernet

            Fernet(v.encode())
        except Exception as exc:
            raise ValueError("TWITCH_TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc
        return v

    @model_validator(mode="after")
    def require_twitch_token_encryption_in_deployed_runtime(self) -> BaseServiceSettings:
        if not self.is_development and not self.twitch_token_encryption_key:
            raise ValueError("TWITCH_TOKEN_ENCRYPTION_KEY is required outside development")
        return self
