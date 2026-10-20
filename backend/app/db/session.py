"""SQLAlchemy 2 database engine and session configuration for Neon PostgreSQL with pgvector."""

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Base declarative class for all SQLAlchemy models."""

    pass


# Async engine for FastAPI request handling (Neon pooled connection)
async_engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=settings.DB_POOL_PRE_PING,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    echo=settings.DEBUG,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Sync engine for Alembic migrations and administrative CLI tasks
def get_sync_engine(database_url: str | None = None) -> Any:
    """Create a synchronous SQLAlchemy engine for sync tasks."""
    url = database_url or settings.DATABASE_URL
    return create_engine(
        url,
        pool_pre_ping=settings.DB_POOL_PRE_PING,
        echo=settings.DEBUG,
    )


SyncSessionLocal = sessionmaker(
    bind=get_sync_engine(),
    autocommit=False,
    autoflush=False,
    class_=Session,
)
