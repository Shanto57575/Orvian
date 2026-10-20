"""Application configuration loaded exclusively from root .env using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qs, urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Canonical repository root is the parent of the backend directory.
# The repository root .env file is the ONLY configuration file loaded by the application.
BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
CANONICAL_ENV_FILE = REPO_ROOT / ".env"


def escape_alembic_url(url: str) -> str:
    """Escape percent signs in database URLs for Python ConfigParser interpolation."""
    return url.replace("%", "%%")


def validate_neon_ssl_mode(url: str, field_name: str, is_direct: bool = False) -> str:
    """Validate that database URLs enforce sslmode=require and reject invalid configurations."""
    # Normalize protocol first
    normalized_url = url
    if normalized_url.startswith("postgres://"):
        normalized_url = normalized_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif normalized_url.startswith("postgresql://") and not normalized_url.startswith(
        "postgresql+"
    ):
        normalized_url = normalized_url.replace("postgresql://", "postgresql+psycopg://", 1)

    parsed = urlparse(normalized_url)
    hostname = (parsed.hostname or "").lower()
    query = parse_qs(parsed.query, keep_blank_values=True)

    # 1. Reject duplicate or conflicting sslmode parameters
    sslmode_list = query.get("sslmode", [])
    if len(sslmode_list) > 1:
        raise ValueError(f"{field_name} contains duplicate 'sslmode' parameters: {sslmode_list}.")

    sslmode = sslmode_list[0].lower() if sslmode_list else ""
    is_local = hostname in ("localhost", "127.0.0.1", "")
    is_neon = "neon.tech" in hostname

    # 2. Enforce sslmode=require for Neon and remote databases
    if (is_neon or not is_local) and sslmode != "require":
        raise ValueError(
            f"{field_name} must enforce 'sslmode=require' for Neon and remote databases. "
            f"Received sslmode='{sslmode or 'none'}' for host '{hostname}'."
        )

    # 3. Reject pooled Neon connections for DIRECT_DATABASE_URL
    if is_direct and is_neon and "-pooler" in hostname:
        raise ValueError(
            f"{field_name} cannot use a pooled Neon connection ('{hostname}'). "
            "A direct (unpooled) connection string is required for schema migrations."
        )

    return normalized_url


class Settings(BaseSettings):
    """Orvian application settings."""

    model_config = SettingsConfigDict(
        # The repository root .env file is the ONLY canonical environment file.
        env_file=str(CANONICAL_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    PROJECT_NAME: str = "Orvian"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Database (Neon PostgreSQL with pgvector)
    DATABASE_URL: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/orvian",
        description="Runtime database connection string (Neon pooled endpoint).",
    )
    DIRECT_DATABASE_URL: str | None = Field(
        default=None,
        description="Direct unpooled database connection string required for Alembic migrations.",
    )
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_PRE_PING: bool = True
    DB_POOL_TIMEOUT: int = 30

    # Authentication & Session Security (Planned for Post-Setup)
    AUTH_SECRET_KEY: str = Field(
        default="development-insecure-secret-key-32-bytes-minimum-length!",
        description="Secret key for signing sessions and tokens.",
    )
    AUTH_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    SESSION_COOKIE_NAME: str = "orvian_session"
    SESSION_COOKIE_SECURE: bool = False
    SESSION_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"

    # Google OAuth (Planned for Post-Setup)
    GOOGLE_OAUTH_CLIENT_ID: str | None = None
    GOOGLE_OAUTH_CLIENT_SECRET: str | None = None
    GOOGLE_OAUTH_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # SMTP Configuration (Planned for Post-Setup)
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str = "noreply@orvian.local"
    SMTP_FROM_NAME: str = "Orvian Assistant"

    # AI Configuration (Planned for Post-Setup)
    OPENAI_API_KEY: str | None = None
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TIMEOUT_SECONDS: int = 30

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        return validate_neon_ssl_mode(v, "DATABASE_URL", is_direct=False)

    @field_validator("DIRECT_DATABASE_URL")
    @classmethod
    def validate_direct_database_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return validate_neon_ssl_mode(v, "DIRECT_DATABASE_URL", is_direct=True)

    @property
    def migration_database_url(self) -> str:
        """Return DIRECT_DATABASE_URL for Alembic migrations.

        Neon pooled connections (PgBouncer transaction mode) do not support DDL operations
        and locks required by Alembic. A direct connection URL is strictly required.
        """
        if not self.DIRECT_DATABASE_URL:
            raise ValueError(
                "DIRECT_DATABASE_URL is required for schema migrations. "
                "Never run migrations through a pooled connection."
            )
        return self.DIRECT_DATABASE_URL


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
