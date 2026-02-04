"""Twitch bot configuration"""

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# === Path Configuration ===
TWITCH_DIR = Path(__file__).parent.parent
BACKEND_DIR = TWITCH_DIR.parent
COMPONENTS_DIR = TWITCH_DIR / "components"
DATA_DIR = BACKEND_DIR / "data"

BOT_SCOPES = [
    # Core bot functionality
    "user:bot",  # Bot identifier
    "user:read:chat",  # Read chat messages
    "user:write:chat",  # Send chat messages
    # Moderation (requires bot to be mod in channel)
    "moderator:read:followers",  # Follow EventSub
    "moderator:manage:announcements",  # Send announcements
    # Optional features
    "user:manage:whispers",  # Whisper messages
]

BROADCASTER_SCOPES = [
    # Minimal scopes - broadcaster just grants bot access
    "channel:bot",  # Allow bot to join channel
    "channel:read:redemptions",  # Channel points EventSub
    "channel:read:subscriptions",  # Subscription EventSub
    "channel:manage:vips",  # VIP redemption
    "bits:read",  # Bits EventSub
]


class TwitchBotSettings(BaseSettings):
    """Twitch bot settings"""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Twitch OAuth
    client_id: str = Field(..., description="Twitch OAuth Client ID")
    client_secret: str = Field(..., description="Twitch OAuth Client Secret")

    # Bot Configuration
    bot_id: str = Field(..., description="Bot User ID")
    owner_id: str = Field(..., description="Owner User ID")

    # Database
    database_url: str = Field(..., description="PostgreSQL database URL")

    # EventSub
    conduit_id: str = Field(default="", description="Twitch EventSub Conduit ID")

    # Frontend
    frontend_url: str = Field(default="http://localhost:3000", description="Frontend URL for OAuth")

    # OpenRouter AI
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openrouter_model: str = Field(
        default="tngtech/deepseek-r1t2-chimera:free", description="OpenRouter model"
    )

    # Environment
    log_level: str = Field(default="INFO", description="Logging level")

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL starts with postgresql://"""
        if not v.startswith("postgresql://"):
            raise ValueError("DATABASE_URL must start with 'postgresql://'")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            logger.warning(f"Invalid log level '{v}', defaulting to INFO")
            return "INFO"
        return v_upper


@lru_cache
def get_settings() -> TwitchBotSettings:
    """Get cached settings instance"""
    return TwitchBotSettings()  # type: ignore[call-arg]


# ============================================
# Backward Compatibility Functions
# ============================================
# These functions maintain compatibility with existing code
# that uses the old env.py interface


def validate_env_vars() -> None:
    """
    Validate required environment variables (backward compatible).

    This function maintains compatibility with code that previously
    imported from env.py. It now uses Pydantic Settings validation.
    """
    try:
        get_settings()
        logger.info("All required environment variables validated successfully")
    except Exception as e:
        # Use "Bot" logger to match old behavior
        bot_logger = logging.getLogger("Bot")
        bot_logger.error(f"Environment validation failed: {e}")
        raise ValueError(str(e)) from e


def load_env_config() -> dict[str, str]:
    """
    Load and return environment configuration as dict (backward compatible).

    This function maintains compatibility with code that previously
    imported from env.py. It now uses Pydantic Settings.
    """
    settings = get_settings()
    return {
        "CLIENT_ID": settings.client_id,
        "CLIENT_SECRET": settings.client_secret,
        "BOT_ID": settings.bot_id,
        "OWNER_ID": settings.owner_id,
        "DATABASE_URL": settings.database_url,
        "CONDUIT_ID": settings.conduit_id,
    }
