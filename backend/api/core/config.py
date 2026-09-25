"""Application configuration using Pydantic Settings"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import SettingsConfigDict

from shared.config_base import DATA_DIR, RUNTIME_DIR, BaseServiceSettings, dev_env_files

__all__ = ["DATA_DIR", "RUNTIME_DIR", "Settings", "get_settings"]


class Settings(BaseServiceSettings):
    model_config = SettingsConfigDict(
        env_file=dev_env_files("api"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Twitch OAuth accepts legacy short aliases during migration.
    client_id: str = Field(..., validation_alias=AliasChoices("client_id", "twitch_client_id"))
    client_secret: str = Field(
        ..., validation_alias=AliasChoices("client_secret", "twitch_client_secret")
    )

    # Nightbot OAuth — only needed for importing commands from Nightbot.
    # Leave unset and the Nightbot import source is hidden from the dashboard;
    # StreamElements import needs no credentials at all.
    nightbot_client_id: str = Field(default="", description="Nightbot OAuth application client ID")
    nightbot_client_secret: str = Field(
        default="", description="Nightbot OAuth application client secret"
    )

    jwt_secret_key: str = Field(..., description="Secret key for JWT token signing")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_expire_days: int = Field(default=7, description="JWT token expiration in days")

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

    @field_validator("payment_encryption_key")
    @classmethod
    def validate_payment_encryption_key(cls, v: str) -> str:
        if not v:
            return v
        try:
            from cryptography.fernet import Fernet

            Fernet(v.encode())
        except Exception as exc:
            raise ValueError("PAYMENT_ENCRYPTION_KEY must be a valid Fernet key") from exc
        return v

    @model_validator(mode="after")
    def require_payment_encryption_in_deployed_runtime(self) -> Settings:
        if not self.is_development and not self.payment_encryption_key:
            raise ValueError("PAYMENT_ENCRYPTION_KEY is required outside development")
        return self

    @property
    def cors_origins(self) -> list[str]:
        return [self.frontend_url]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
