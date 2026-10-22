"""Tests for application configuration, Neon SSL enforcement, URL parsing, and Alembic escaping."""

import pytest

from app.config import (
    BACKEND_DIR,
    CANONICAL_ENV_FILE,
    Settings,
    escape_alembic_url,
)


def test_canonical_env_file_location() -> None:
    """Verify CANONICAL_ENV_FILE points strictly to backend/.env."""
    assert CANONICAL_ENV_FILE == BACKEND_DIR / ".env"
    assert CANONICAL_ENV_FILE.name == ".env"


def test_database_url_coercion() -> None:
    """Verify postgres:// and postgresql:// are normalized to postgresql+psycopg://."""
    s1 = Settings(DATABASE_URL="postgres://user:pass@ep-test.neon.tech/neondb?sslmode=require")
    assert s1.DATABASE_URL.startswith("postgresql+psycopg://")

    s2 = Settings(DATABASE_URL="postgresql://user:pass@ep-test.neon.tech/neondb?sslmode=require")
    assert s2.DATABASE_URL.startswith("postgresql+psycopg://")


def test_neon_ssl_mode_enforced_for_neon_hosts() -> None:
    """Verify Neon hosts without sslmode=require raise ValueError."""
    # Missing sslmode
    with pytest.raises(ValueError, match="must enforce 'sslmode=require'"):
        Settings(DATABASE_URL="postgresql://user:pass@ep-test.us-east-2.aws.neon.tech/neondb")

    # Invalid sslmode
    with pytest.raises(ValueError, match="must enforce 'sslmode=require'"):
        Settings(
            DATABASE_URL="postgresql://user:pass@ep-test.us-east-2.aws.neon.tech/neondb?sslmode=prefer"
        )


def test_neon_ssl_mode_enforced_for_direct_database_url() -> None:
    """Verify DIRECT_DATABASE_URL validates sslmode=require for Neon hosts."""
    with pytest.raises(ValueError, match="must enforce 'sslmode=require'"):
        Settings(
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/orvian",
            DIRECT_DATABASE_URL="postgresql://user:pass@ep-direct.neon.tech/neondb?sslmode=disable",
        )


def test_reject_duplicate_sslmode_parameters() -> None:
    """Verify duplicate sslmode parameters in query strings are strictly rejected."""
    with pytest.raises(ValueError, match="duplicate 'sslmode' parameters"):
        Settings(
            DATABASE_URL=(
                "postgresql://user:pass@ep-test.neon.tech/neondb?sslmode=require&sslmode=disable"
            )
        )

    with pytest.raises(ValueError, match="duplicate 'sslmode' parameters"):
        Settings(
            DATABASE_URL=(
                "postgresql://user:pass@ep-test.neon.tech/neondb?sslmode=require&sslmode=require"
            )
        )


def test_reject_pooled_neon_url_as_direct_database_url() -> None:
    """Verify pooled Neon URLs (-pooler in host) are rejected for DIRECT_DATABASE_URL."""
    with pytest.raises(ValueError, match="cannot use a pooled Neon connection"):
        Settings(
            DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/orvian",
            DIRECT_DATABASE_URL=(
                "postgresql://user:pass@ep-test-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"
            ),
        )


def test_accept_valid_direct_neon_url_for_direct_database_url() -> None:
    """Verify direct unpooled Neon URL is accepted for DIRECT_DATABASE_URL."""
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/orvian",
        DIRECT_DATABASE_URL=(
            "postgresql://user:pass@ep-test.us-east-2.aws.neon.tech/neondb?sslmode=require"
        ),
    )
    assert settings.DIRECT_DATABASE_URL is not None
    assert "-pooler" not in settings.DIRECT_DATABASE_URL
    assert "sslmode=require" in settings.DIRECT_DATABASE_URL


def test_local_database_url_permitted_without_ssl() -> None:
    """Verify localhost/127.0.0.1 development and test databases are permitted without SSL."""
    s = Settings(DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/orvian_test")
    assert "localhost:5432" in s.DATABASE_URL


def test_migration_database_url_requires_direct_url_and_does_not_silently_fallback() -> None:
    """Verify migration_database_url raises ValueError when DIRECT_DATABASE_URL is not set."""
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/orvian",
        DIRECT_DATABASE_URL=None,
    )
    with pytest.raises(ValueError, match="DIRECT_DATABASE_URL is required for schema migrations"):
        _ = settings.migration_database_url


def test_migration_database_url_returns_normalized_direct_url() -> None:
    """Verify migration_database_url returns direct connection string when set."""
    settings = Settings(
        DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/orvian",
        DIRECT_DATABASE_URL="postgresql://user:pass@localhost:5432/orvian_direct",
    )
    assert settings.migration_database_url.startswith("postgresql+psycopg://")
    assert "orvian_direct" in settings.migration_database_url


def test_escape_alembic_url_escapes_percent_signs() -> None:
    """Verify percent signs in passwords are escaped for ConfigParser interpolation."""
    raw_url = "postgresql+psycopg://user:p%40ss%25word@ep-test.neon.tech/neondb?sslmode=require"
    escaped = escape_alembic_url(raw_url)
    assert "%%40" in escaped
    assert "%%25" in escaped
    assert escaped == raw_url.replace("%", "%%")
