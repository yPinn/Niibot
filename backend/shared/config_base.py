"""Shared base settings for all Niibot services."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

LOGGER: logging.Logger = logging.getLogger(__name__)

# ── Shared filesystem layout ─────────────────────────────────────────────────
# Single source of truth for backend paths — each service config re-exports
# DATA_DIR / RUNTIME_DIR from here so the three services can't drift.
#
# `shared/config_base.py` sits at backend/shared/, so .parent.parent is the
# backend root in both local checkouts and Docker images (where /app == backend).
_BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = _BACKEND_DIR / "data"  # static repo content baked into image
RUNTIME_DIR = _BACKEND_DIR / "runtime"  # mutable state, volume-mounted per env

try:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    # Read-only FS (some test/CI sandboxes) — writers will surface a clearer
    # error on first save attempt.
    LOGGER.warning("Could not pre-create RUNTIME_DIR %s", RUNTIME_DIR, exc_info=True)


class BaseServiceSettings(BaseSettings):
    """Common settings shared across api, discord, and twitch services.

    Each subclass must define its own ``model_config`` with the correct
    ``env_file`` tuple (shared.env first, service .env second).
    """

    # Database
    database_url: str = Field(..., description="PostgreSQL database URL")

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")

    # Environment
    environment: str = Field(default="development", description="Runtime environment name")

    # Error reporting
    error_webhook_url: str = Field(default="", description="Discord webhook URL for error alerts")

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
