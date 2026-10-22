"""FastAPI dependency guards for session resolution, CSRF validation, and authorization."""

import secrets
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.security import hash_token
from app.config import get_settings
from app.db.models import User, UserSession
from app.db.session import get_db_session

settings = get_settings()


async def get_current_session(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
) -> UserSession:
    """Resolve active user session from HttpOnly cookie or Authorization Bearer header."""
    raw_token = request.cookies.get(settings.SESSION_COOKIE_NAME)

    if not raw_token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header.split(" ", 1)[1].strip()

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please log in.",
        )

    token_hash = hash_token(raw_token)
    now = datetime.now(UTC)

    result = await db.execute(
        select(UserSession)
        .options(selectinload(UserSession.user))
        .where(
            UserSession.token_hash == token_hash,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
    )
    session = result.scalar_one_or_none()

    if not session or not session.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session has expired or been revoked. Please sign in again.",
        )

    if not session.user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Please contact support.",
        )

    if session.credential_version != session.user.credential_version:
        session.revoked_at = now
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account credentials were changed. Please sign in again.",
        )

    return session


async def get_current_user(
    session: UserSession = Depends(get_current_session),
) -> User:
    """Extract authenticated user entity from active session."""
    return session.user


async def require_verified_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Enforce that the user has verified their email address before accessing features."""
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email verification required. Please verify your email to access this feature.",
        )
    return current_user


def require_role(required_role: str) -> Callable[[User], User]:
    """Factory creating an account-level authorization dependency."""

    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role != required_role and current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: requires '{required_role}' privileges.",
            )
        return current_user

    return role_checker


def validate_csrf(request: Request) -> None:
    """Validate CSRF double-submit token on state-mutating requests
    when a cookie session is active.
    """
    # CSRF protection applies when requests use browser cookie sessions
    has_session_cookie = bool(request.cookies.get(settings.SESSION_COOKIE_NAME))

    if has_session_cookie and request.method in (
        "POST",
        "PUT",
        "DELETE",
        "PATCH",
    ):
        csrf_cookie = request.cookies.get(settings.CSRF_COOKIE_NAME)
        csrf_header = request.headers.get("X-CSRF-Token")

        if (
            not csrf_cookie
            or not csrf_header
            or not secrets.compare_digest(csrf_cookie, csrf_header)
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF validation failed. Missing or invalid X-CSRF-Token.",
            )
