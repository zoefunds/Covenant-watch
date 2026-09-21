"""
Central, typed configuration. All runtime config comes from environment
variables (see .env.example) -- nothing is hardcoded, nothing is guessed.
"""
from __future__ import annotations

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- App ---
    ENV: str = Field(default="development")
    APP_NAME: str = Field(default="covenant-watch-backend")
    LOG_LEVEL: str = Field(default="INFO")

    # --- Database ---
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://covenant:covenant@localhost:5432/covenant_watch"
    )

    # --- Auth / sessions ---
    SESSION_SECRET: str = Field(
        default="dev-only-insecure-secret-change-me",
        description="Signing key for session cookies (itsdangerous). MUST be overridden in prod.",
    )
    SESSION_TTL_SECONDS: int = Field(default=60 * 60 * 12)  # 12h
    NONCE_TTL_SECONDS: int = Field(default=5 * 60)  # 5 minutes
    SESSION_COOKIE_NAME: str = Field(default="cw_session")
    COOKIE_SECURE: bool = Field(default=True, description="Set False only for local http dev")
    COOKIE_DOMAIN: Optional[str] = Field(default=None)

    # --- GenLayer chain / contract ---
    CONTRACT_ADDRESS: Optional[str] = Field(
        default=None,
        description="Set only after the user deploys covenant_watch.py themselves.",
    )
    GENLAYER_NETWORK: str = Field(
        default="studionet", description="One of: localnet, studionet, testnet_asimov, testnet_bradbury"
    )
    GENLAYER_RPC_URL: Optional[str] = Field(
        default=None, description="Override RPC URL; if unset, uses the network's default."
    )
    INDEXER_POLL_INTERVAL_SECONDS: int = Field(default=8)
    INDEXER_ENABLED: bool = Field(default=True)

    # --- CORS ---
    CORS_ALLOWED_ORIGINS: str = Field(
        default="http://localhost:3000",
        description="Comma-separated list of allowed frontend origins.",
    )

    # --- Rate limiting (defense in depth only; contract is the real enforcer) ---
    RATE_LIMIT_AUTH: str = Field(default="10/minute")
    RATE_LIMIT_WRITE_ADJACENT: str = Field(default="30/minute")

    # --- Observability ---
    SENTRY_DSN: Optional[str] = Field(default=None)

    @field_validator("COOKIE_SECURE", mode="before")
    @classmethod
    def _coerce_bool(cls, v):
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.CORS_ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
