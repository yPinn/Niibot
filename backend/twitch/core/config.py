"""Twitch bot configuration"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from shared.config_base import BaseServiceSettings

# === Path Configuration ===
TWITCH_DIR = Path(__file__).resolve().parent.parent
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
    "moderator:manage:shoutouts",  # Shoutout on raid
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


class TwitchBotSettings(BaseServiceSettings):
    """Twitch bot settings"""

    model_config = SettingsConfigDict(
        # Order mirrors docker-compose.yml: shared.env first, twitch/.env overrides.
        # shared.env.local (gitignored) overrides shared.env for local dev (e.g. localhost DB).
        env_file=(
            Path(__file__).parent.parent.parent / "shared.env",
            Path(__file__).parent.parent.parent / "shared.env.local",
            Path(__file__).parent.parent / ".env",
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Twitch OAuth
    twitch_client_id: str = Field(..., description="Twitch OAuth Client ID")
    twitch_client_secret: str = Field(..., description="Twitch OAuth Client Secret")

    # Bot Configuration
    bot_id: str = Field(..., description="Bot User ID")
    owner_id: str = Field(..., description="Owner User ID")

    # EventSub
    conduit_id: str = Field(default="", description="Twitch EventSub Conduit ID")

    # Frontend
    frontend_url: str = Field(default="http://localhost:3000", description="Frontend URL for OAuth")

    # OpenRouter AI
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openrouter_model: str = Field(default="", description="OpenRouter model")

    # YouTube Data API
    youtube_api_key: str = Field(default="", description="YouTube Data API v3 key")

    # Server
    port: int = Field(default=4344, description="Health server port")


@lru_cache
def get_settings() -> TwitchBotSettings:
    """Get cached settings instance"""
    return TwitchBotSettings()  # type: ignore[call-arg]
