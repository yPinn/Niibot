"""Application configuration using Pydantic Settings"""

import logging
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Twitch OAuth
    client_id: str = Field(..., description="Twitch OAuth Client ID")
    client_secret: str = Field(..., description="Twitch OAuth Client Secret")

    # Discord OAuth (選填，用於 Discord 登入)
    discord_client_id: str = Field(default="", description="Discord OAuth Client ID")
    discord_client_secret: str = Field(default="", description="Discord OAuth Client Secret")

    # JWT Configuration
    jwt_secret_key: str = Field(..., description="Secret key for JWT token signing")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_expire_days: int = Field(default=30, description="JWT token expiration in days")

    # Database
    database_url: str = Field(..., description="PostgreSQL database URL")

    # Server URLs
    frontend_url: str = Field(default="http://localhost:3000", description="Frontend URL for CORS")
    api_url: str = Field(default="http://localhost:8000", description="API server URL")
    twitch_bot_url: str = Field(
        default="http://localhost:4344", description="Twitch Bot Health Server URL"
    )
    discord_bot_url: str = Field(
        default="http://localhost:8080", description="Discord Bot Health Server URL"
    )

    # Environment
    environment: str = Field(default="development", description="Environment name")
    log_level: str = Field(default="INFO", description="Logging level")

    # Server Configuration
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")

    # Keep-Alive (Render)
    enable_keep_alive: bool = Field(default=True, description="Enable heartbeat keep-alive task")
    keep_alive_interval: int = Field(default=300, description="Heartbeat interval in seconds")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is a valid logging level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            logger.warning(f"Invalid log level '{v}', defaulting to INFO")
            return "INFO"
        return v_upper

    @property
    def cors_origins(self) -> list[str]:
        """Get CORS allowed origins"""
        return [self.frontend_url]

    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.environment.lower() == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()  # type: ignore[call-arg]
