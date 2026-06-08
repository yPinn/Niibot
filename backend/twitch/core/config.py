"""Twitch bot configuration"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from shared.config_base import BaseServiceSettings
from shared.twitch_scopes import BOT_SCOPES, BROADCASTER_SCOPES

# === Path Configuration ===
TWITCH_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = TWITCH_DIR.parent
COMPONENTS_DIR = TWITCH_DIR / "components"
DATA_DIR = BACKEND_DIR / "data"  # static repo content baked into image
RUNTIME_DIR = BACKEND_DIR / "runtime"  # mutable state, volume-mounted per env
# Ensure the runtime dir exists at process start; writers can save without
# each duplicating mkdir logic.
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

__all__ = ["BOT_SCOPES", "BROADCASTER_SCOPES"]


class TwitchBotSettings(BaseServiceSettings):
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

    twitch_client_id: str = Field(..., description="Twitch OAuth Client ID")
    twitch_client_secret: str = Field(..., description="Twitch OAuth Client Secret")
    bot_id: str = Field(..., description="Bot User ID")
    owner_id: str = Field(..., description="Owner User ID")
    conduit_id: str = Field(default="", description="Twitch EventSub Conduit ID")
    frontend_url: str = Field(default="http://localhost:3000", description="Frontend URL for OAuth")
    groq_api_key: str = Field(default="", description="Groq API key (free tier, no billing)")
    groq_model: str = Field(default="", description="Groq model (default: llama-3.3-70b-versatile)")
    gemini_api_key: str = Field(
        default="", description="Gemini AI Studio API key (free, no billing)"
    )
    gemini_model: str = Field(default="", description="Gemini model (default: gemini-1.5-flash)")
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openrouter_model: str = Field(default="", description="OpenRouter model")
    youtube_api_key: str = Field(default="", description="YouTube Data API v3 key")
    port: int = Field(default=4344, description="Health server port")


@lru_cache
def get_settings() -> TwitchBotSettings:
    return TwitchBotSettings()  # type: ignore[call-arg]
