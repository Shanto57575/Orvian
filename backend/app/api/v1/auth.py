"""Authentication and account lifecycle endpoints."""

import base64
import hashlib
import logging
import secrets
from typing import Any
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    get_current_session,
    get_current_user,
    require_verified_user,
    validate_csrf,
)
from app.auth.limiter import limiter
from app.auth.oauth import (
    exchange_google_code_for_user_info,
    generate_oauth_state,
    get_google_authorization_url,
    is_google_oauth_configured,
)
from app.auth.security import generate_csrf_token
from app.auth.service import AuthService
from app.config import get_settings
from app.db.models import User, UserSession
from app.db.session import get_db_session
from app.schemas.auth import (
    AuthResponse,
    ForgotPasswordRequest,
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    ResendOtpRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SessionResponse,
    UserResponse,
    VerifyEmailRequest,
    VerifyOtpRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()

OAUTH_STATE_COOKIE = "orvian_oauth_state"
OAUTH_VERIFIER_COOKIE = "orvian_oauth_verifier"


def _set_auth_cookies(
    response: Response, raw_token: str, csrf_token: str, max_age_seconds: int
) -> None:
    """Attach secure session and CSRF cookies to the HTTP response."""
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        max_age=max_age_seconds,
        path="/",
    )
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,  # Accessible to frontend for X-CSRF-Token header
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        max_age=max_age_seconds,
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    """Clear session and CSRF cookies across all browsers."""
    response.delete_cookie(
        key=settings.SESSION_COOKIE_NAME,
        path="/",
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        httponly=True,
    )
    response.delete_cookie(
        key=settings.CSRF_COOKIE_NAME,
        path="/",
        secure=settings.SESSION_COOKIE_SECURE,
        samesite=settings.SESSION_COOKIE_SAMESITE,
        httponly=False,
    )


@router.post(
    "/register",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("3/minute")
async def register(
    request: Request,
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Register a new user account with mandatory email verification and 6-digit OTP."""
    return await AuthService.register_user(db, data)


@router.post(
    "/verify-otp",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("5/minute")
async def verify_otp(
    request: Request,
    response: Response,
    data: VerifyOtpRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    """Validate 6-digit OTP, verify email, and automatically log in with session cookies."""
    user, raw_session_token, csrf_token, max_age = await AuthService.verify_otp(
        db,
        email=data.email,
        otp=data.otp,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_auth_cookies(response, raw_session_token, csrf_token, max_age)
    return AuthResponse(
        user=UserResponse.model_validate(user),
        message="Email verified successfully. Welcome to Orvian!",
        csrf_token=csrf_token,
    )


@router.post("/resend-otp", response_model=MessageResponse)
@limiter.limit("3/minute")
async def resend_otp(
    request: Request,
    data: ResendOtpRequest,
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Request a fresh 6-digit verification OTP."""
    return await AuthService.resend_otp(db, data.email)


@router.post(
    "/login",
    response_model=AuthResponse,
    status_code=status.HTTP_200_OK,
)
@limiter.limit("5/minute")
async def login(
    request: Request,
    response: Response,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    """Authenticate email and password credentials and establish a secure session."""
    user = await AuthService.authenticate_local(db, data.email, data.password)

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    raw_token, _, expires_at = await AuthService.create_user_session(
        db, user.id, client_ip, user_agent
    )
    csrf_token = generate_csrf_token()

    max_age = int(settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400)
    _set_auth_cookies(response, raw_token, csrf_token, max_age)

    return AuthResponse(
        user=UserResponse.model_validate(user),
        message="Login successful.",
        csrf_token=csrf_token,
    )


@router.post(
    "/logout",
    response_model=MessageResponse,
    dependencies=[Depends(validate_csrf)],
)
async def logout(
    response: Response,
    session: UserSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Revoke the active session and remove session cookies."""
    await AuthService.revoke_session_by_hash(db, session.token_hash)
    _clear_auth_cookies(response)
    return MessageResponse(message="Successfully signed out.")


@router.post(
    "/logout-all",
    response_model=MessageResponse,
    dependencies=[Depends(validate_csrf)],
)
async def logout_all(
    response: Response,
    session: UserSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Revoke all active sessions for the current user across all devices."""
    await AuthService.revoke_all_user_sessions(db, session.user_id)
    _clear_auth_cookies(response)
    return MessageResponse(message="Successfully signed out of all devices.")


@router.post("/verify-email", response_model=AuthResponse)
async def verify_email(
    request: Request,
    response: Response,
    data: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db_session),
) -> AuthResponse:
    """Consume a single-use verification token to mark an account verified and establish session."""
    user, session_token, csrf_token, max_age_seconds = await AuthService.verify_email_token(
        db,
        data.token,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    _set_auth_cookies(response, session_token, csrf_token, max_age_seconds)
    return AuthResponse(
        user=UserResponse.model_validate(user),
        csrf_token=csrf_token,
        message="Email verified successfully.",
    )


@router.post("/resend-verification", response_model=MessageResponse)
@limiter.limit("3/minute")
async def resend_verification(
    request: Request,
    data: ResendVerificationRequest,
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Request a fresh single-use verification email link."""
    message = await AuthService.resend_verification_email(db, data.email)
    return MessageResponse(message=message)


@router.post("/forgot-password", response_model=MessageResponse)
@limiter.limit("3/minute")
async def forgot_password(
    request: Request,
    data: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Request password reset instructions."""
    message = await AuthService.request_password_reset(db, data.email)
    return MessageResponse(message=message)


@router.post("/reset-password", response_model=MessageResponse)
async def reset_password(
    data: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db_session),
) -> MessageResponse:
    """Reset account password using a single-use token and invalidate all sessions."""
    await AuthService.reset_password(db, data.token, data.new_password)
    return MessageResponse(
        message="Password reset successfully. Please log in with your new password."
    )


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """Retrieve profile and verification status of current authenticated user."""
    return UserResponse.model_validate(current_user)


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    current_session: UserSession = Depends(get_current_session),
    db: AsyncSession = Depends(get_db_session),
) -> list[SessionResponse]:
    """List active sessions for the current user."""
    result = await db.execute(
        select(UserSession)
        .where(
            UserSession.user_id == current_session.user_id,
            UserSession.revoked_at.is_(None),
        )
        .order_by(UserSession.created_at.desc())
    )
    sessions = result.scalars().all()
    return [
        SessionResponse(
            id=s.id,
            created_at=s.created_at,
            expires_at=s.expires_at,
            ip_address=s.ip_address,
            user_agent=s.user_agent,
            is_current=(s.id == current_session.id),
        )
        for s in sessions
    ]


@router.get("/google/login")
async def google_login() -> Response:
    """Initiate Google OAuth 2.0 PKCE flow."""
    if not is_google_oauth_configured():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                "Google OAuth is not configured. Set GOOGLE_OAUTH_CLIENT_ID "
                "and GOOGLE_OAUTH_CLIENT_SECRET in the root .env file."
            ),
        )

    state = generate_oauth_state()
    code_verifier = secrets.token_urlsafe(64)
    hashed_challenge = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    code_challenge = base64.urlsafe_b64encode(hashed_challenge).decode("utf-8").rstrip("=")

    auth_url = await get_google_authorization_url(state, code_challenge)

    response = RedirectResponse(url=auth_url, status_code=status.HTTP_302_FOUND)
    # Store PKCE verifier and state in temporary short-lived cookies
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=state,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=600,
        path="/api/v1/auth/google",
    )
    response.set_cookie(
        key=OAUTH_VERIFIER_COOKIE,
        value=code_verifier,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        max_age=600,
        path="/api/v1/auth/google",
    )
    return response


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    """Handle Google OAuth callback, verify state/PKCE, and establish session."""

    def _oauth_error_response(detail: str) -> RedirectResponse:
        url = f"{settings.FRONTEND_URL}/?auth_error={quote_plus(detail)}"
        res = RedirectResponse(url=url, status_code=status.HTTP_302_FOUND)
        res.delete_cookie(key=OAUTH_STATE_COOKIE, path="/api/v1/auth/google")
        res.delete_cookie(key=OAUTH_VERIFIER_COOKIE, path="/api/v1/auth/google")
        return res

    if error:
        return _oauth_error_response(f"Google authentication was denied: {error}")

    saved_state = request.cookies.get(OAUTH_STATE_COOKIE)
    code_verifier = request.cookies.get(OAUTH_VERIFIER_COOKIE)

    if not code or not state or not saved_state or not secrets.compare_digest(state, saved_state):
        return _oauth_error_response("OAuth state validation failed. Potential CSRF attempt.")

    if not code_verifier:
        return _oauth_error_response("OAuth PKCE verifier missing from session.")

    try:
        user_info = await exchange_google_code_for_user_info(code, code_verifier)
        user = await AuthService.handle_google_user(db, user_info)
    except HTTPException as exc:
        return _oauth_error_response(str(exc.detail))
    except Exception as exc:
        logger.error("Unexpected error during Google callback: %s", exc)
        return _oauth_error_response("Failed to complete Google authentication. Please try again.")

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    raw_token, _, _ = await AuthService.create_user_session(db, user.id, client_ip, user_agent)
    csrf_token = generate_csrf_token()
    max_age = int(settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400)

    # Redirect to frontend callback page
    frontend_redirect_url = f"{settings.FRONTEND_URL}/auth/callback"
    response = RedirectResponse(url=frontend_redirect_url, status_code=status.HTTP_302_FOUND)
    _set_auth_cookies(response, raw_token, csrf_token, max_age)

    # Clean up temporary OAuth handshake cookies
    response.delete_cookie(key=OAUTH_STATE_COOKIE, path="/api/v1/auth/google")
    response.delete_cookie(key=OAUTH_VERIFIER_COOKIE, path="/api/v1/auth/google")
    return response


@router.get("/protected-verification-check")
async def check_verified_access(
    current_user: User = Depends(require_verified_user),
) -> dict[str, Any]:
    """Test endpoint accessible exclusively to verified users."""
    return {
        "status": "granted",
        "email": current_user.email,
        "is_verified": current_user.is_verified,
    }
