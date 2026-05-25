"""Application configuration using Pydantic Settings"""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import SettingsConfigDict

from shared.config_base import BaseServiceSettings


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(
        # Order mirrors docker-compose.yml: shared.env first, api/.env overrides.
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

    # Twitch OAuth — reads TWITCH_CLIENT_ID/SECRET from shared.env via alias
    client_id: str = Field(..., validation_alias=AliasChoices("client_id", "twitch_client_id"))
    client_secret: str = Field(
        ..., validation_alias=AliasChoices("client_secret", "twitch_client_secret")
    )

    jwt_secret_key: str = Field(..., description="Secret key for JWT token signing")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_expire_days: int = Field(default=30, description="JWT token expiration in days")

    frontend_url: str = Field(default="http://localhost:3000", description="Frontend URL for CORS")
    api_url: str = Field(default="http://localhost:8000", description="API server URL")
    twitch_bot_url: str = Field(
        default="http://localhost:4344", description="Twitch Bot Health Server URL"
    )
    discord_bot_url: str = Field(
        default="http://localhost:8080", description="Discord Bot Health Server URL"
    )

    # Bot/owner identity (shared with twitch bot via shared.env)
    bot_id: str = Field(default="", description="Twitch bot user ID")
    owner_id: str = Field(default="", description="Owner Twitch user ID")

    payment_encryption_key: str = Field(
        default="",
        description=(
            "Fernet key for encrypting payment gateway credentials (hash_key/hash_iv) at rest. "
            'Generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        ),
    )
    youtube_api_key: str = Field(default="", description="YouTube Data API v3 key")
    releases_github_token: str = Field(
        default="", description="GitHub PAT for reading private repo releases"
    )
    discord_public_key: str = Field(
        default="", description="Discord application public key for webhook signature verification"
    )
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    @field_validator("frontend_url", "api_url", "twitch_bot_url", "discord_bot_url", mode="before")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("jwt_algorithm")
    @classmethod
    def validate_jwt_algorithm(cls, v: str) -> str:
        allowed = {"HS256", "HS384", "HS512"}
        if v not in allowed:
            raise ValueError(f"jwt_algorithm must be one of {sorted(allowed)}, got '{v}'")
        return v

    @property
    def cors_origins(self) -> list[str]:
        return [self.frontend_url]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
