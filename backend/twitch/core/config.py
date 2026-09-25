"""Twitch bot configuration"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import SettingsConfigDict

from shared.config_base import DATA_DIR, RUNTIME_DIR, BaseServiceSettings, dev_env_files
from shared.twitch_scopes import BOT_SCOPES, BROADCASTER_SCOPES

# === Path Configuration ===
TWITCH_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = TWITCH_DIR.parent
COMPONENTS_DIR = TWITCH_DIR / "components"

__all__ = ["BOT_SCOPES", "BROADCASTER_SCOPES", "DATA_DIR", "RUNTIME_DIR"]


class TwitchBotSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(
        env_file=dev_env_files("twitch"),
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
    groq_model: str = Field(default="", description="Groq model; required when GROQ_API_KEY is set")
    gemini_api_key: str = Field(
        default="", description="Gemini AI Studio API key (free, no billing)"
    )
    gemini_model: str = Field(
        default="", description="Gemini model; required when GEMINI_API_KEY is set"
    )
    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    openrouter_model: str = Field(
        default="", description="OpenRouter model; required when OPENROUTER_API_KEY is set"
    )
    youtube_api_key: str = Field(default="", description="YouTube Data API v3 key")
    port: int = Field(default=4344, description="Health server port")


@lru_cache
def get_settings() -> TwitchBotSettings:
    return TwitchBotSettings()  # type: ignore[call-arg]
