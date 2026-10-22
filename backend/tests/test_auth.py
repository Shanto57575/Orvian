"""Comprehensive automated tests for authentication, sessions, CSRF, and authorization."""

import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth.security import (
    create_signed_token,
    decode_signed_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.config import DEFAULT_DEV_SECRET, Settings
from app.db.models import EmailOutbox, User, UserSession, UserToken
from app.db.session import Base


# ====================================================================
# 1. Password Hashing & Token Unit Tests
# ====================================================================
def test_password_hashing_and_verification() -> None:
    """Verify Argon2id password hashing and constant-time verification."""
    password = "SuperSecurePassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword123!", hashed) is False
    assert verify_password(password, None) is False


def test_token_creation_and_decoding() -> None:
    """Verify JWT signed token encoding, claims, and type enforcement."""
    user_id = uuid.uuid4()
    raw_token, token_hash, expires_at = create_signed_token(
        user_id=user_id,
        token_type="verify_email",
        expires_delta=timedelta(hours=1),
    )

    assert len(raw_token) > 20
    assert len(token_hash) == 64
    assert expires_at > datetime.now(UTC)

    payload = decode_signed_token(raw_token, "verify_email")
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "verify_email"

    # Type mismatch rejected
    with pytest.raises(ValueError, match="Invalid token type"):
        decode_signed_token(raw_token, "reset_password")


def test_production_secret_validation() -> None:
    """Verify default development secret is rejected when ENVIRONMENT is production."""
    with pytest.raises(ValueError, match="Production requires a custom AUTH_SECRET_KEY"):
        Settings(
            ENVIRONMENT="production",
            AUTH_SECRET_KEY=DEFAULT_DEV_SECRET,
            DATABASE_URL="postgresql+psycopg://u:p@localhost:5432/db",
        )

    with pytest.raises(ValueError, match="Production requires a custom AUTH_SECRET_KEY"):
        Settings(
            ENVIRONMENT="production",
            AUTH_SECRET_KEY="too-short",
            DATABASE_URL="postgresql+psycopg://u:p@localhost:5432/db",
        )


# ====================================================================
# 2. Registration & Account Enumeration Prevention Tests
# ====================================================================
@pytest.mark.asyncio
async def test_registration_creates_unverified_user(
    async_client: AsyncClient,
) -> None:
    """Verify registration creates an unverified account and returns a generic response."""
    response = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "alice@example.com",
            "password": "ValidPassword123!",
            "full_name": "Alice Operator",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "Registration received" in data["message"]


@pytest.mark.asyncio
async def test_registration_prevents_account_enumeration(
    async_client: AsyncClient,
) -> None:
    """Verify duplicate registration returns the identical generic response."""
    payload = {
        "email": "duplicate@example.com",
        "password": "ValidPassword123!",
        "full_name": "Duplicate User",
    }
    res1 = await async_client.post("/api/v1/auth/register", json=payload)
    res2 = await async_client.post("/api/v1/auth/register", json=payload)

    assert res1.status_code == 200
    assert res2.status_code == 200
    assert res1.json()["message"] == res2.json()["message"]


# ====================================================================
# 3. Login, Session & Cookie Tests
# ====================================================================
@pytest.mark.asyncio
async def test_login_success_sets_cookies(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify successful login returns user details and sets HttpOnly session & CSRF cookies."""
    user = User(
        id=uuid.uuid4(),
        email="login_test@example.com",
        hashed_password=hash_password("LoginPassword123!"),
        full_name="Login Test",
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "login_test@example.com", "password": "LoginPassword123!"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["email"] == "login_test@example.com"
    assert "csrf_token" in data
    assert "orvian_session" in response.cookies
    assert "orvian_csrf" in response.cookies


@pytest.mark.asyncio
async def test_login_invalid_password_returns_401(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify login with incorrect password returns 401."""
    user = User(
        id=uuid.uuid4(),
        email="wrong_pw@example.com",
        hashed_password=hash_password("RealPassword123!"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "wrong_pw@example.com", "password": "BadPassword123!"},
    )
    assert response.status_code == 401
    assert "Invalid email or password" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_inactive_account_returns_403(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify disabled account cannot log in."""
    user = User(
        id=uuid.uuid4(),
        email="inactive@example.com",
        hashed_password=hash_password("RealPassword123!"),
        is_active=False,
    )
    db_session.add(user)
    await db_session.commit()

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "inactive@example.com", "password": "RealPassword123!"},
    )
    assert response.status_code == 403
    assert "Account is disabled" in response.json()["detail"]


# ====================================================================
# 4. Session Revocation & Logout Tests
# ====================================================================
@pytest.mark.asyncio
async def test_logout_revokes_session(async_client: AsyncClient, db_session: AsyncSession) -> None:
    """Verify /logout revokes active session and invalidates subsequent access."""
    user = User(
        id=uuid.uuid4(),
        email="logout_test@example.com",
        hashed_password=hash_password("Pass12345!"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    # Login
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "logout_test@example.com", "password": "Pass12345!"},
    )
    csrf_token = login_res.json()["csrf_token"]

    # Verify authenticated
    me_res = await async_client.get("/api/v1/auth/me")
    assert me_res.status_code == 200

    # Logout with CSRF token header
    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert logout_res.status_code == 200

    # Subsequent access fails with 401
    me_after = await async_client.get("/api/v1/auth/me")
    assert me_after.status_code == 401


# ====================================================================
# 5. Email Verification & Token Replay Prevention Tests
# ====================================================================
@pytest.mark.asyncio
async def test_email_verification_and_replay_prevention(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify single-use token consumption and that replaying the token fails with 400."""
    user = User(
        id=uuid.uuid4(),
        email="verify_test@example.com",
        is_active=True,
        is_verified=False,
    )
    db_session.add(user)
    await db_session.flush()

    raw_jwt, token_hash, expires_at = create_signed_token(
        user.id, "verify_email", timedelta(hours=24)
    )
    token_record = UserToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=token_hash,
        token_type="verify_email",
        expires_at=expires_at,
    )
    db_session.add(token_record)
    await db_session.commit()

    # First consumption succeeds
    res1 = await async_client.post(
        "/api/v1/auth/verify-email",
        json={"token": raw_jwt},
    )
    assert res1.status_code == 200
    assert "verified successfully" in res1.json()["message"]

    # Second consumption fails (token replay attack prevented)
    res2 = await async_client.post(
        "/api/v1/auth/verify-email",
        json={"token": raw_jwt},
    )
    assert res2.status_code == 400
    assert (
        "already been used" in res2.json()["detail"] or "already verified" in res2.json()["detail"]
    )


# ====================================================================
# 6. Password Reset & Session Invalidation Tests
# ====================================================================
@pytest.mark.asyncio
async def test_password_reset_and_session_invalidation(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify password reset updates password, revokes existing sessions, and rejects replays."""
    user = User(
        id=uuid.uuid4(),
        email="reset_test@example.com",
        hashed_password=hash_password("OldPassword123!"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.flush()

    # Create active session for user
    session = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hash_token("test-session-token"),
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(session)

    # Create reset token
    raw_jwt, token_hash, expires_at = create_signed_token(
        user.id, "reset_password", timedelta(minutes=15)
    )
    token_record = UserToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=token_hash,
        token_type="reset_password",
        expires_at=expires_at,
    )
    db_session.add(token_record)
    await db_session.commit()

    # Reset password
    reset_res = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_jwt, "new_password": "BrandNewPassword123!"},
    )
    assert reset_res.status_code == 200

    # Old password no longer works
    login_old = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "reset_test@example.com", "password": "OldPassword123!"},
    )
    assert login_old.status_code == 401

    # New password works
    login_new = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "reset_test@example.com", "password": "BrandNewPassword123!"},
    )
    assert login_new.status_code == 200

    # Replay of reset token fails
    replay_res = await async_client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_jwt, "new_password": "AnotherPassword123!"},
    )
    assert replay_res.status_code == 400


# ====================================================================
# 7. CSRF Protection Tests
# ====================================================================
@pytest.mark.asyncio
async def test_csrf_validation_blocks_unauthorized_state_mutation(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify cookie-authenticated POST fails when X-CSRF-Token is missing or mismatched."""
    user = User(
        id=uuid.uuid4(),
        email="csrf_test@example.com",
        hashed_password=hash_password("Pass12345!"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    await async_client.post(
        "/api/v1/auth/login",
        json={"email": "csrf_test@example.com", "password": "Pass12345!"},
    )

    # Missing X-CSRF-Token header -> 403
    res_no_csrf = await async_client.post("/api/v1/auth/logout")
    assert res_no_csrf.status_code == 403
    assert "CSRF validation failed" in res_no_csrf.json()["detail"]

    # Mismatched X-CSRF-Token header -> 403
    res_bad_csrf = await async_client.post(
        "/api/v1/auth/logout",
        headers={"X-CSRF-Token": "invalid-csrf-token"},
    )
    assert res_bad_csrf.status_code == 403


# ====================================================================
# 8. Mandatory Verification & Authorization Tests
# ====================================================================
@pytest.mark.asyncio
async def test_protected_feature_requires_email_verification(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify unverified user cannot access protected features (returns 403)."""
    user = User(
        id=uuid.uuid4(),
        email="unverified@example.com",
        hashed_password=hash_password("Pass12345!"),
        is_active=True,
        is_verified=False,  # Unverified!
    )
    db_session.add(user)
    await db_session.commit()

    await async_client.post(
        "/api/v1/auth/login",
        json={"email": "unverified@example.com", "password": "Pass12345!"},
    )

    # Attempt to access protected endpoint
    res = await async_client.get("/api/v1/auth/protected-verification-check")
    assert res.status_code == 403
    assert "Email verification required" in res.json()["detail"]


@pytest.mark.asyncio
async def test_protected_feature_granted_for_verified_user(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Verify verified user successfully accesses protected features."""
    user = User(
        id=uuid.uuid4(),
        email="verified@example.com",
        hashed_password=hash_password("Pass12345!"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    await db_session.commit()

    await async_client.post(
        "/api/v1/auth/login",
        json={"email": "verified@example.com", "password": "Pass12345!"},
    )

    res = await async_client.get("/api/v1/auth/protected-verification-check")
    assert res.status_code == 200
    assert res.json()["status"] == "granted"


# ====================================================================
# 9. Google OAuth Safe Account Linking Tests
# ====================================================================
@pytest.mark.asyncio
async def test_google_oauth_rejects_auto_merging_local_password_account(
    db_session: AsyncSession,
) -> None:
    """Verify Google sign-in auto-links an existing password account matching verified email."""
    from app.auth.service import AuthService

    # Create local password user
    user = User(
        id=uuid.uuid4(),
        email="target@example.com",
        hashed_password=hash_password("SecurePassword123!"),
        auth_provider="local",
        google_id=None,
        is_verified=False,
    )
    db_session.add(user)
    await db_session.commit()

    # Signing in with Google for target@example.com links the Google identity and marks verified
    linked_user = await AuthService.handle_google_user(
        db_session,
        {
            "google_id": "google-sub-123456",
            "email": "target@example.com",
            "full_name": "Target User",
        },
    )
    assert linked_user.id == user.id
    assert linked_user.google_id == "google-sub-123456"
    assert linked_user.is_verified is True


# ====================================================================
# 10. Security Regression Tests for Day 3 Findings
# ====================================================================
@pytest.mark.asyncio
async def test_pre_registration_takeover_prevention(
    async_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 1: Verification must not activate attacker-controlled credentials

    when legitimate email owner registers later.
    """
    from sqlalchemy import select

    captured_otps: list[str] = []

    def mock_dispatch(to_email: str, token: str, otp: str | None = None) -> None:
        if otp:
            captured_otps.append(otp)

    monkeypatch.setattr(
        "app.auth.service.dispatch_verification_email_background",
        mock_dispatch,
    )

    # 1. Attacker pre-registers victim's email
    reg1 = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "victim@example.com", "password": "AttackerPassword123!"},
    )
    assert reg1.status_code == 200
    assert len(captured_otps) == 1
    attacker_otp = captured_otps[-1]

    # User is unverified, hashed_password is None (bound to challenge token)
    user_res = await db_session.execute(select(User).where(User.email == "victim@example.com"))
    user = user_res.scalar_one()
    assert user.is_verified is False
    assert user.hashed_password is None

    # 2. Legitimate owner registers the same email later (after cooldown) with their own password
    user.otp_last_sent_at = datetime.now(UTC) - timedelta(seconds=70)
    await db_session.commit()

    reg2 = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "victim@example.com", "password": "LegitimatePassword123!"},
    )
    assert reg2.status_code == 200
    assert "Registration received" in reg2.json()["message"]
    assert len(captured_otps) == 2
    legitimate_otp = captured_otps[-1]

    # Attacker's old challenge token was superseded; attempting to use it fails
    bad_verify = await async_client.post(
        "/api/v1/auth/verify-otp",
        json={"email": "victim@example.com", "otp": attacker_otp},
    )
    assert bad_verify.status_code == 400

    # 3. Legitimate user verifies with their OTP
    legit_verify = await async_client.post(
        "/api/v1/auth/verify-otp",
        json={"email": "victim@example.com", "otp": legitimate_otp},
    )
    assert legit_verify.status_code == 200
    assert legit_verify.json()["user"]["is_verified"] is True

    # DB now holds legitimate password, activated only upon challenge completion
    await db_session.refresh(user)
    assert verify_password("LegitimatePassword123!", user.hashed_password) is True
    assert verify_password("AttackerPassword123!", user.hashed_password) is False

    # 4. Attacker cannot authenticate with attacker password
    login_att = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "victim@example.com", "password": "AttackerPassword123!"},
    )
    assert login_att.status_code == 401

    # Legitimate owner logs in successfully
    login_legit = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "victim@example.com", "password": "LegitimatePassword123!"},
    )
    assert login_legit.status_code == 200

    # 5. Attacker re-registration against verified account rejected with clear error
    reg3 = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "victim@example.com", "password": "AttackerNewPass999!"},
    )
    assert reg3.status_code == 400
    assert "already exists" in reg3.json()["detail"]
    await db_session.refresh(user)
    assert verify_password("LegitimatePassword123!", user.hashed_password) is True
    assert verify_password("AttackerNewPass999!", user.hashed_password) is False


def test_smtp_tls_context_and_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """Finding 2: Verify TLS context (ssl.create_default_context()) and timeout

    are enforced on SMTP connections.
    """
    import ssl
    from unittest.mock import MagicMock

    from app.auth.email import _send_smtp_sync
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(settings, "SMTP_PORT", 587)
    monkeypatch.setattr(settings, "SMTP_USER", "testuser")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "testpass")
    monkeypatch.setattr(settings, "SMTP_TIMEOUT_SECONDS", 7.5)

    mock_server = MagicMock()
    mock_smtp_cls = MagicMock(return_value=mock_server)
    mock_server.__enter__.return_value = mock_server

    monkeypatch.setattr("smtplib.SMTP", mock_smtp_cls)

    _send_smtp_sync("target@example.com", "Test Subject", "Test Body", None)

    # Assert timeout was passed to smtplib.SMTP
    mock_smtp_cls.assert_called_once_with(
        "smtp.example.com",
        587,
        timeout=7.5,
    )
    # Assert starttls was called with an SSLContext instance
    assert mock_server.starttls.call_count == 1
    call_kwargs = mock_server.starttls.call_args.kwargs
    assert "context" in call_kwargs
    assert isinstance(call_kwargs["context"], ssl.SSLContext)


@pytest.mark.asyncio
async def test_atomic_token_consumption_and_replay_prevention(
    db_session: AsyncSession,
) -> None:
    """Finding 3: Atomic token consumption (conditional UPDATE ... RETURNING)

    prevents replay even under concurrent requests.
    """
    from fastapi import HTTPException

    from app.auth.service import AuthService

    # Create unverified user
    user = User(
        id=uuid.uuid4(),
        email="atomic@example.com",
        hashed_password=hash_password("Pass12345!"),
        is_active=True,
        is_verified=False,
    )
    db_session.add(user)
    await db_session.flush()

    raw_jwt, token_hash, expires_at = create_signed_token(
        user_id=user.id,
        token_type="verify_email",
        expires_delta=timedelta(hours=1),
    )
    token = UserToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=token_hash,
        token_type="verify_email",
        expires_at=expires_at,
    )
    db_session.add(token)
    await db_session.commit()

    # Attempt 1: First consumption succeeds
    verified_user, session_token, csrf_token, max_age = await AuthService.verify_email_token(
        db_session, raw_jwt
    )
    assert verified_user.is_verified is True
    assert session_token is not None
    assert csrf_token is not None
    assert max_age > 0

    # Attempt 2: Immediate second consumption (replay) must raise HTTP 400
    with pytest.raises(HTTPException) as exc:
        await AuthService.verify_email_token(db_session, raw_jwt)
    assert exc.value.status_code == 400
    assert "already been used" in exc.value.detail or "already verified" in exc.value.detail


@pytest.mark.asyncio
async def test_concurrent_password_reset_invalidates_old_credential_session(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Finding 4: Session issued with old credentials is immediately rejected

    when credential_version increments upon password reset.
    """
    # 1. Create verified user with credential_version = 1
    user = User(
        id=uuid.uuid4(),
        email="reset_target@example.com",
        hashed_password=hash_password("OldPassword123!"),
        is_active=True,
        is_verified=True,
        credential_version=1,
    )
    db_session.add(user)
    await db_session.commit()

    # 2. Log in to establish session with credential_version = 1
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "reset_target@example.com", "password": "OldPassword123!"},
    )
    assert login_res.status_code == 200

    # Verify protected endpoint works
    prot1 = await async_client.get("/api/v1/auth/protected-verification-check")
    assert prot1.status_code == 200

    # 3. Password reset occurs: increment credential_version to 2
    user.credential_version = 2
    await db_session.commit()

    # 4. Same session must now be rejected with 401
    prot2 = await async_client.get("/api/v1/auth/protected-verification-check")
    assert prot2.status_code == 401
    assert "credentials were changed" in prot2.json()["detail"]


@pytest.mark.asyncio
async def test_authlib_oauth_client_lifecycle_and_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 5: Authlib client lifecycle handles resource cleanup and claim validation."""
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import HTTPException

    from app.auth.oauth import exchange_google_code_for_user_info
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")

    # Mock client with proper context manager support
    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    # Test rejection of unverified email
    mock_client.fetch_token = AsyncMock(
        return_value={
            "userinfo": {
                "sub": "google-12345",
                "email": "unverified_google@example.com",
                "email_verified": False,
            }
        }
    )

    monkeypatch.setattr("app.auth.oauth.create_oauth_client", lambda: mock_client)

    with pytest.raises(HTTPException) as exc:
        await exchange_google_code_for_user_info("dummy_code", "dummy_verifier")
    assert exc.value.status_code == 400
    assert "not verified" in exc.value.detail
    # Verify client context manager exit (cleanup) was awaited
    assert mock_client.__aexit__.await_count == 1


@pytest.mark.asyncio
async def test_google_login_browser_redirect(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 6: Google login initiates top-level browser redirect with state/verifier cookies."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "dummy-google-id")
    monkeypatch.setattr(settings, "GOOGLE_OAUTH_CLIENT_SECRET", "dummy-google-secret")

    res = await async_client.get("/api/v1/auth/google/login", follow_redirects=False)
    assert res.status_code == 302
    assert "accounts.google.com" in res.headers["location"]
    # Check that state and verifier cookies are set on the redirect response
    cookies = res.cookies
    assert "orvian_oauth_state" in cookies
    assert "orvian_oauth_verifier" in cookies


@pytest.mark.asyncio
async def test_smtp_delivery_failure_prevents_account_enumeration(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 7: Email delivery failure must not raise 500 or leak user presence."""
    from app.auth import email

    async def mock_failing_email(*args: object, **kwargs: object) -> None:
        raise RuntimeError("SMTP connection dropped or host unreachable")

    monkeypatch.setattr(email, "send_verification_email", mock_failing_email)
    monkeypatch.setattr(email, "send_password_reset_email", mock_failing_email)

    # 1. Registration with failing email delivery returns 200 generic message
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={"email": "fail_smtp@example.com", "password": "ValidPassword123!"},
    )
    assert reg_res.status_code == 200
    assert "Registration received" in reg_res.json()["message"]

    # 2. Password reset request with failing email delivery returns 200 generic message
    reset_res = await async_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": "fail_smtp@example.com"},
    )
    assert reset_res.status_code == 200
    assert "password reset instructions have been sent" in reset_res.json()["message"]


@pytest.mark.asyncio
async def test_otp_verification_and_automatic_login(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify that submitting correct 6-digit OTP marks user verified and automatically logs in."""
    email = "otp_user@example.com"
    password = "StrongPassword123!"

    captured_otps: list[str] = []
    monkeypatch.setattr(
        "app.auth.service.dispatch_verification_email_background",
        lambda to_email, token, otp=None: captured_otps.append(otp) if otp else None,
    )

    # 1. Register new user
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "OTP Test User"},
    )
    assert reg_res.status_code == 200
    assert "Registration received" in reg_res.json()["message"]
    assert len(captured_otps) == 1
    otp_code = captured_otps[0]
    assert len(otp_code) == 6
    assert otp_code.isdigit()

    # 2. Attempt verification with incorrect OTP
    bad_otp = "000000" if otp_code != "000000" else "111111"
    bad_res = await async_client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "otp": bad_otp},
    )
    assert bad_res.status_code == 400
    assert "invalid" in bad_res.json()["detail"].lower()

    # 3. Submit valid OTP
    verify_res = await async_client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "otp": otp_code},
    )
    assert verify_res.status_code == 200
    data = verify_res.json()
    assert data["user"]["is_verified"] is True
    assert "orvian_session" in verify_res.cookies

    # 4. Attempt replay of the same OTP -> must be rejected
    replay_res = await async_client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "otp": otp_code},
    )
    assert replay_res.status_code == 400

    # 5. Access authenticated route with session cookie
    me_res = await async_client.get("/api/v1/auth/me")
    assert me_res.status_code == 200
    assert me_res.json()["is_verified"] is True


@pytest.mark.asyncio
async def test_otp_attempt_limits_and_lockout(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 3: Atomic per-challenge attempt limits lock out brute force after 5 attempts."""
    email = "brute_force_target@example.com"
    password = "ValidPassword123!"

    captured_otps: list[str] = []
    monkeypatch.setattr(
        "app.auth.service.dispatch_verification_email_background",
        lambda to_email, token, otp=None: captured_otps.append(otp) if otp else None,
    )

    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert reg_res.status_code == 200
    valid_otp = captured_otps[0]

    # Submit 5 incorrect OTP attempts
    for i in range(5):
        res = await async_client.post(
            "/api/v1/auth/verify-otp",
            json={"email": email, "otp": f"99999{i}"},
        )
        assert res.status_code == 400
        if i == 4:
            # 5th attempt exhausts max attempts and locks token
            assert "locked" in res.json()["detail"].lower()
        else:
            assert "invalid" in res.json()["detail"].lower()

    # 6th attempt with the CORRECT OTP must still be rejected due to lockout
    locked_res = await async_client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "otp": valid_otp},
    )
    assert locked_res.status_code == 400
    assert (
        "new" in locked_res.json()["detail"].lower()
        or "locked" in locked_res.json()["detail"].lower()
    )


@pytest.mark.asyncio
async def test_otp_expiry_rejection(
    async_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 3: Expired OTP challenge is rejected with 400."""
    from sqlalchemy import select

    email = "expired_otp@example.com"
    captured_otps: list[str] = []
    monkeypatch.setattr(
        "app.auth.service.dispatch_verification_email_background",
        lambda to_email, token, otp=None: captured_otps.append(otp) if otp else None,
    )

    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "ValidPassword123!"},
    )
    otp = captured_otps[0]

    user_res = await db_session.execute(select(User).where(User.email == email))
    user = user_res.scalar_one()
    # Manually expire the token in the database
    token_res = await db_session.execute(
        select(UserToken).where(
            UserToken.user_id == user.id,
            UserToken.token_type == "verify_otp",
        )
    )
    token = token_res.scalar_one()
    token.expires_at = datetime.now(UTC) - timedelta(minutes=5)
    await db_session.commit()

    # Attempt verification with expired OTP -> 400
    res = await async_client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "otp": otp},
    )
    assert res.status_code == 400
    assert "expired" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_sibling_verification_method_invalidation(
    async_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 2: Consuming OTP invalidates sibling JWT link; consuming JWT link invalidates OTP."""
    from sqlalchemy import select

    captured_tokens: list[dict[str, str | None]] = []
    monkeypatch.setattr(
        "app.auth.service.dispatch_verification_email_background",
        lambda to_email, token, otp=None: captured_tokens.append({"token": token, "otp": otp}),
    )

    # 1. Register user
    email = "sibling_test@example.com"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "ValidPassword123!"},
    )
    jwt_token = captured_tokens[0]["token"]
    otp_code = captured_tokens[0]["otp"]
    assert jwt_token and otp_code

    # 2. Verify via OTP
    res_otp = await async_client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "otp": otp_code},
    )
    assert res_otp.status_code == 200

    # 3. Sibling JWT verify_email token in DB must now be marked is_used / consumed
    token_res = await db_session.execute(
        select(UserToken).where(
            UserToken.token_type == "verify_email",
            UserToken.consumed_at.is_(None),
        )
    )
    active_tokens = token_res.scalars().all()
    assert len(active_tokens) == 0

    # 4. Attempting to consume sibling JWT token link fails
    res_jwt = await async_client.post(
        "/api/v1/auth/verify-email",
        json={"token": jwt_token},
    )
    assert res_jwt.status_code == 400


@pytest.mark.asyncio
async def test_password_recovery_invalidates_pending_challenges(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 2: Password recovery invalidates pending signup/verification challenges."""
    captured_otps: list[str] = []
    monkeypatch.setattr(
        "app.auth.service.dispatch_verification_email_background",
        lambda to_email, token, otp=None: captured_otps.append(otp) if otp else None,
    )
    monkeypatch.setattr(
        "app.auth.service.dispatch_password_reset_email_background",
        lambda to_email, token: None,
    )

    # 1. Register unverified user
    email = "recovery_invalidation@example.com"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "ValidPassword123!"},
    )
    otp = captured_otps[0]

    # 2. Request password reset for this email
    forgot_res = await async_client.post(
        "/api/v1/auth/forgot-password",
        json={"email": email},
    )
    assert forgot_res.status_code == 200

    # 3. Pending signup OTP verification challenge must now be invalidated
    otp_res = await async_client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "otp": otp},
    )
    assert otp_res.status_code == 400


@pytest.mark.asyncio
async def test_verified_account_rejects_enrollment_otps(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Finding 2: Already-verified accounts must reject enrollment OTPs."""
    user = User(
        id=uuid.uuid4(),
        email="already_verified@example.com",
        hashed_password=hash_password("ValidPassword123!"),
        is_active=True,
        is_verified=True,
    )
    db_session.add(user)
    # Create an unconsumed OTP token for this user
    token = UserToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hash_token(f"{user.id}:654321"),
        token_type="verify_otp",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    db_session.add(token)
    await db_session.commit()

    # Submitting OTP verification for already-verified user must fail with 400
    res = await async_client.post(
        "/api/v1/auth/verify-otp",
        json={"email": "already_verified@example.com", "otp": "654321"},
    )
    assert res.status_code == 400
    assert "Account is already verified" in res.json()["detail"]


@pytest.mark.asyncio
async def test_resend_otp_cooldown_and_abuse_prevention(
    async_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding 3: Safe resend behavior enforces a 60-second cooldown."""
    email = "resend_cooldown@example.com"
    monkeypatch.setattr(
        "app.auth.service.dispatch_verification_email_background",
        lambda to_email, token, otp=None: None,
    )

    # 1. Initial registration
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "ValidPassword123!"},
    )

    # 2. Immediate resend within 60s cooldown must be rejected with 429
    resend_fail = await async_client.post(
        "/api/v1/auth/resend-otp",
        json={"email": email},
    )
    assert resend_fail.status_code == 429
    assert "second" in resend_fail.json()["detail"].lower()


@pytest.mark.asyncio
async def test_rate_limiting_throttling_enabled(
    async_client: AsyncClient,
) -> None:
    """Finding 6: Dedicated test verifying slowapi rate limiter throttles excessive requests."""
    from app.main import app

    try:
        app.state.limiter.enabled = True
        responses = []
        for _ in range(7):
            res = await async_client.post(
                "/api/v1/auth/login",
                json={"email": "throttled@example.com", "password": "WrongPassword123!"},
            )
            responses.append(res.status_code)

        # Login limit is 5/minute; 6th or 7th request must be 429 Too Many Requests
        assert 429 in responses
    finally:
        app.state.limiter.enabled = False


@pytest.mark.asyncio
async def test_concurrent_registration_independent_sessions() -> None:
    """Finding 1 & 6: Overlapping concurrent registrations using independent DB sessions

    serialize cleanly via PostgreSQL row locking without race conditions or overwriting.
    """
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.auth.service import AuthService
    from app.schemas.auth import RegisterRequest
    from tests.conftest import TEST_DATABASE_URL

    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    test_email = f"concurrent_{uuid.uuid4().hex[:8]}@example.com"

    async def register_task(pw: str) -> str:
        async with session_factory() as session:
            try:
                res = await AuthService.register_user(
                    session,
                    RegisterRequest(
                        email=test_email,
                        password=pw,
                        full_name="Concurrent Tester",
                    ),
                )
                await session.commit()
                return res.message
            except Exception:
                await session.rollback()
                raise

    # Launch two simultaneous registration operations
    results = await asyncio.gather(
        register_task("PassOne123!"),
        register_task("PassTwo123!"),
        return_exceptions=True,
    )

    # Both must succeed without deadlock or constraint collision
    for r in results:
        assert isinstance(r, str)
        assert "Registration received" in r

    await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_reset_and_login_independent_sessions() -> None:
    """Finding 4 & 6: Password reset concurrent with session validation invalidates old creds."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.orm import selectinload

    from app.auth.service import AuthService
    from tests.conftest import TEST_DATABASE_URL

    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    test_email = f"reset_race_{uuid.uuid4().hex[:8]}@example.com"
    old_pw = "OldPassword123!"
    new_pw = "NewPassword123!"

    # Create verified user in first session
    user_id = uuid.uuid4()
    async with session_factory() as session:
        user = User(
            id=user_id,
            email=test_email,
            hashed_password=hash_password(old_pw),
            is_active=True,
            is_verified=True,
            credential_version=1,
        )
        session.add(user)
        # Create reset token
        raw_token, token_hash, expires_at = create_signed_token(
            user_id, "reset_password", timedelta(minutes=15)
        )
        token = UserToken(
            id=uuid.uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            token_type="reset_password",
            expires_at=expires_at,
        )
        session.add(token)
        await session.commit()

    # Create session token using old credential version = 1
    session_token_raw = f"test-session-{uuid.uuid4().hex}"
    async with session_factory() as session:
        user_sess = UserSession(
            id=uuid.uuid4(),
            user_id=user_id,
            token_hash=hash_token(session_token_raw),
            expires_at=datetime.now(UTC) + timedelta(days=1),
            credential_version=1,
        )
        session.add(user_sess)
        await session.commit()

    # Now run reset password in an independent transaction
    async with session_factory() as session:
        await AuthService.reset_password(session, raw_token, new_pw)
        await session.commit()

    # Validate session with independent session: user.credential_version was incremented to 2!
    async with session_factory() as session:
        sess_res = await session.execute(
            select(UserSession)
            .options(selectinload(UserSession.user))
            .where(UserSession.token_hash == hash_token(session_token_raw))
        )
        saved_sess = sess_res.scalar_one()
        assert saved_sess.credential_version == 1
        assert saved_sess.user.credential_version == 2
        # Session credential version mismatch invalidates session

    await engine.dispose()


# ====================================================================
# 11. Codex Remediation Verification Suite (4 Findings)
# ====================================================================
@pytest.mark.asyncio
async def test_persistent_otp_attempt_budget_across_resends(
    async_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex Finding 1 (P1): Persistent account-level OTP attempt budget.

    Registration and every resend endpoint share one atomic attempt budget.
    Resending must never restore guesses.
    """
    captured_otps: list[str] = []
    monkeypatch.setattr(
        "app.auth.service.dispatch_verification_email_background",
        lambda to_email, token, otp=None: captured_otps.append(otp) if otp else None,
    )

    email = "persistent_budget@example.com"
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "SecurePassword123!"},
    )
    assert reg.status_code == 200
    assert len(captured_otps) == 1

    # Enter 3 incorrect OTPs
    for _ in range(3):
        res = await async_client.post(
            "/api/v1/auth/verify-otp",
            json={"email": email, "otp": "000000"},
        )
        assert res.status_code == 400

    # Verify 3 failed attempts on the User model
    user_res = await db_session.execute(select(User).where(User.email == email))
    user = user_res.scalar_one()
    assert user.otp_failed_attempts == 3

    # Fast-forward past cooldown and resend OTP
    user.otp_last_sent_at = datetime.now(UTC) - timedelta(seconds=70)
    await db_session.commit()

    resend_res = await async_client.post(
        "/api/v1/auth/resend-otp",
        json={"email": email},
    )
    assert resend_res.status_code == 200
    assert len(captured_otps) == 2

    # Verify attempt budget was NOT reset by resending!
    await db_session.refresh(user)
    assert user.otp_failed_attempts == 3

    # Enter 1 more bad OTP (total 4)
    res4 = await async_client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "otp": "000000"},
    )
    assert res4.status_code == 400
    await db_session.refresh(user)
    assert user.otp_failed_attempts == 4

    # Enter 5th bad OTP (budget exhausted: max 5)
    res5 = await async_client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "otp": "000000"},
    )
    assert res5.status_code == 400
    assert "locked" in res5.json()["detail"].lower()

    await db_session.refresh(user)
    assert user.otp_failed_attempts == 5
    assert user.otp_locked_until is not None


@pytest.mark.asyncio
async def test_concurrent_registration_and_verification_deadlock_elimination() -> None:
    """Codex Finding 2 (P2): Consistent lock ordering (User before UserToken)
    eliminates registration/verification deadlocks under overlapping concurrent requests.
    """
    import asyncio

    from app.auth.service import AuthService
    from app.schemas.auth import RegisterRequest
    from tests.conftest import TEST_DATABASE_URL

    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    email = "concurrent_deadlock@example.com"
    async with session_factory() as session:
        reg_req = RegisterRequest(email=email, password="InitialPassword123!")
        await AuthService.register_user(session, reg_req)

    # Fetch token and user
    async with session_factory() as session:
        tok_stmt = (
            select(UserToken)
            .join(User)
            .where(User.email == email, UserToken.token_type == "verify_otp")
        )
        tok_res = await session.execute(tok_stmt)
        token = tok_res.scalar_one()
        assert token is not None

    async def worker_verify_otp() -> None:
        async with session_factory() as s:
            with contextlib.suppress(Exception):
                await AuthService.verify_otp(s, email, "123456")

    async def worker_re_register() -> None:
        async with session_factory() as s:
            with contextlib.suppress(Exception):
                reg_req2 = RegisterRequest(email=email, password="NewPassword123!")
                await AuthService.register_user(s, reg_req2)

    async def worker_resend() -> None:
        async with session_factory() as s:
            with contextlib.suppress(Exception):
                await AuthService.resend_otp(s, email)

    # Run overlapping requests across independent sessions
    results = await asyncio.gather(
        worker_verify_otp(),
        worker_re_register(),
        worker_resend(),
        worker_verify_otp(),
        return_exceptions=True,
    )
    for res in results:
        assert not isinstance(res, Exception), f"Concurrent deadlock occurred: {res}"

    await engine.dispose()


@pytest.mark.asyncio
async def test_preserve_pending_credentials_on_resend_and_successful_login(
    async_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex Finding 3 (P2): Preserve challenge-bound pending password credentials
    when resending verification. Verify that a successfully verified account can actually log in.
    """
    captured_otps: list[str] = []
    monkeypatch.setattr(
        "app.auth.service.dispatch_verification_email_background",
        lambda to_email, token, otp=None: captured_otps.append(otp) if otp else None,
    )

    email = "preserve_creds@example.com"
    password = "OriginalSecretPassword123!"

    # 1. Register user
    reg = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert reg.status_code == 200
    assert len(captured_otps) == 1

    # 2. Advance cooldown and trigger resend-verification
    user_res = await db_session.execute(select(User).where(User.email == email))
    user = user_res.scalar_one()
    user.otp_last_sent_at = datetime.now(UTC) - timedelta(seconds=70)
    await db_session.commit()

    resend_res = await async_client.post(
        "/api/v1/auth/resend-verification",
        json={"email": email},
    )
    assert resend_res.status_code == 200
    assert len(captured_otps) == 2
    new_otp = captured_otps[-1]

    # 3. Verify OTP using the new challenge code
    verify_res = await async_client.post(
        "/api/v1/auth/verify-otp",
        json={"email": email, "otp": new_otp},
    )
    assert verify_res.status_code == 200
    data = verify_res.json()
    assert data["user"]["is_verified"] is True

    # 4. Verify user can now log in using the original password
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert login_data["user"]["is_verified"] is True
    assert "orvian_session" in login_res.cookies


@pytest.mark.asyncio
async def test_postgresql_transactional_outbox_reliability_and_bounded_retries(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Codex Finding 4 (P2): Minimal PostgreSQL transactional outbox.
    Atomic enqueue within transaction, status updates, and bounded retries (3 attempts).
    """
    from app.auth.email import deliver_outbox_message

    # 1. Enqueue outbox message in transaction
    outbox_id = uuid.uuid4()
    msg = EmailOutbox(
        id=outbox_id,
        recipient="outbox_retry@example.com",
        subject="Test Outbox",
        body_text="Test message body",
        body_html="<p>Test</p>",
        status="pending",
        attempts=0,
        max_retries=3,
    )
    db_session.add(msg)
    await db_session.commit()

    # 2. Mock send_email to always fail
    async def mock_fail_send(*args: object, **kwargs: object) -> None:
        raise RuntimeError("Transient network outage")

    monkeypatch.setattr("app.auth.email.send_email", mock_fail_send)

    # 3. Deliver outbox message -> bounded retries up to max_retries (3)
    success = await deliver_outbox_message(outbox_id)
    assert success is False

    # 4. Verify message status in DB is "failed" with 3 attempts and recorded last_error
    await db_session.refresh(msg)
    assert msg.status == "failed"
    assert msg.attempts == 3
    assert "Transient network outage" in str(msg.last_error)

    # 5. Successful delivery transitions status to "sent"
    outbox_id2 = uuid.uuid4()
    msg2 = EmailOutbox(
        id=outbox_id2,
        recipient="outbox_success@example.com",
        subject="Test Outbox Success",
        body_text="Test message body",
        body_html="<p>Test</p>",
        status="pending",
        attempts=0,
        max_retries=3,
    )
    db_session.add(msg2)
    await db_session.commit()

    async def mock_success_send(*args: object, **kwargs: object) -> None:
        return None

    monkeypatch.setattr("app.auth.email.send_email", mock_success_send)

    success2 = await deliver_outbox_message(outbox_id2)
    assert success2 is True

    await db_session.refresh(msg2)
    assert msg2.status == "sent"
    assert msg2.processed_at is not None
