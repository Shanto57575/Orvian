"""Core authentication service handling registration, login, verification, and OAuth."""

import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.email import (
    dispatch_outbox_delivery,
    enqueue_password_reset_outbox,
    enqueue_verification_outbox,
)
from app.auth.security import (
    create_signed_token,
    decode_signed_token,
    generate_csrf_token,
    generate_numeric_otp,
    generate_session_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.config import get_settings
from app.db.models import User, UserSession, UserToken
from app.schemas.auth import MessageResponse, RegisterRequest

logger = logging.getLogger(__name__)
settings = get_settings()


def _to_utc(dt: datetime) -> datetime:
    """Normalize datetime to timezone-aware UTC across database backends."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def dispatch_verification_email_background(
    to_email: str,
    token: str,
    otp: str | None = None,
) -> None:
    """Dispatches verification notification (intercepted by test hooks if needed)."""
    pass


def dispatch_password_reset_email_background(to_email: str, token: str) -> None:
    """Dispatches password reset notification (intercepted by test hooks if needed)."""
    pass


class AuthService:
    """Authentication and session management workflows."""

    @staticmethod
    async def _get_pending_password_hash(
        db: AsyncSession,
        user: User,
    ) -> str | None:
        """Retrieve latest challenge-bound pending password hash or user password."""
        stmt = (
            select(UserToken.pending_password_hash)
            .where(
                UserToken.user_id == user.id,
                UserToken.pending_password_hash.is_not(None),
            )
            .order_by(UserToken.created_at.desc())
            .limit(1)
        )
        res = await db.execute(stmt)
        pending = res.scalar_one_or_none()
        return pending or user.hashed_password

    @staticmethod
    async def _create_and_send_verification_token(
        db: AsyncSession,
        user: User,
        pending_password_hash: str | None = None,
    ) -> tuple[str, uuid.UUID]:
        """Invalidate old verification tokens, create fresh JWT link & 6-digit OTP bound
        to pending credentials, and enqueue in PostgreSQL outbox. Returns (otp_code, outbox_id).
        """
        now = datetime.now(UTC)
        user.otp_last_sent_at = now

        # Invalidate existing active tokens of verification types
        await db.execute(
            update(UserToken)
            .where(
                UserToken.user_id == user.id,
                UserToken.token_type.in_(["verify_email", "verify_otp"]),
                UserToken.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )

        # 1. JWT Link Token
        raw_jwt, token_hash, expires_at = create_signed_token(
            user_id=user.id,
            token_type="verify_email",
            expires_delta=timedelta(hours=settings.EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS),
        )
        db_token = UserToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            token_type="verify_email",
            expires_at=expires_at,
            pending_password_hash=pending_password_hash,
            attempts=0,
            max_attempts=settings.MAX_OTP_ATTEMPTS,
            last_sent_at=now,
        )
        db.add(db_token)

        # 2. 6-Digit Numeric OTP Token
        otp_code, otp_hash, otp_expires = generate_numeric_otp(user.id, length=6)
        db_otp = UserToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=otp_hash,
            token_type="verify_otp",
            expires_at=otp_expires,
            pending_password_hash=pending_password_hash,
            attempts=0,
            max_attempts=settings.MAX_OTP_ATTEMPTS,
            last_sent_at=now,
        )
        db.add(db_otp)
        await db.flush()

        # Enqueue in PostgreSQL transactional outbox
        outbox_item = enqueue_verification_outbox(db, user.email, raw_jwt, otp=otp_code)
        await db.flush()
        dispatch_verification_email_background(user.email, raw_jwt, otp=otp_code)
        return otp_code, outbox_item.id

    @staticmethod
    async def register_user(
        db: AsyncSession,
        data: RegisterRequest,
    ) -> MessageResponse:
        """Register a new user account with challenge-bound credentials and anti-enumeration."""
        now = datetime.now(UTC)
        generic_message = (
            "Registration received. If this email address is eligible, "
            "a verification code has been sent."
        )

        # Row lock ordering: query by normalized email with FOR UPDATE
        result = await db.execute(select(User).where(User.email == data.email).with_for_update())
        existing_user = result.scalar_one_or_none()

        pwd_hash = hash_password(data.password)

        if existing_user:
            # Finding 1 & 4: Clear, honest error if already registered & verified
            if existing_user.is_verified:
                if existing_user.auth_provider == "google":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "An account with this email already exists using Google. "
                            "Please sign in with Google."
                        ),
                    )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "An account with this email already exists. "
                        "Please sign in with your password."
                    ),
                )

            # Check if account is locked out from prior failed OTP attempts
            if existing_user.otp_locked_until and _to_utc(existing_user.otp_locked_until) > now:
                return MessageResponse(message=generic_message)

            # Check cooldown consistently: if registered too recently, do not resend
            if existing_user.otp_last_sent_at:
                elapsed = (now - _to_utc(existing_user.otp_last_sent_at)).total_seconds()
                if elapsed < settings.RESEND_COOLDOWN_SECONDS:
                    return MessageResponse(message=generic_message)

            # P1: Preserve attempt budget on re-registration (never reset otp_failed_attempts)
            if data.full_name is not None:
                existing_user.full_name = data.full_name
            existing_user.credential_version += 1
            await db.flush()

            # Revoke existing unverified sessions
            await db.execute(
                update(UserSession)
                .where(UserSession.user_id == existing_user.id, UserSession.revoked_at.is_(None))
                .values(revoked_at=now)
            )

            try:
                _, outbox_id = await AuthService._create_and_send_verification_token(
                    db, existing_user, pending_password_hash=pwd_hash
                )
                await db.commit()
                dispatch_outbox_delivery(outbox_id)
            except Exception as e:
                logger.error("Failed to create verification challenge on re-registration: %s", e)
                await db.commit()

            return MessageResponse(message=generic_message)

        # Create new unverified user (hashed_password is None until verified challenge completes!)
        new_user = User(
            id=uuid.uuid4(),
            email=data.email,
            hashed_password=None,  # Credentials bound to challenge, not user row!
            full_name=data.full_name,
            is_active=True,
            is_verified=False,
            role="user",
            auth_provider="local",
            credential_version=1,
            otp_failed_attempts=0,
            otp_last_sent_at=now,
        )
        try:
            db.add(new_user)
            await db.flush()
        except IntegrityError:
            await db.rollback()
            # Handle race condition where another transaction committed this email concurrently
            retry_res = await db.execute(
                select(User).where(User.email == data.email).with_for_update()
            )
            concurrent_user = retry_res.scalar_one_or_none()
            if not concurrent_user:
                return MessageResponse(message=generic_message)
            if concurrent_user.is_verified:
                if concurrent_user.auth_provider == "google":
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "An account with this email already exists using Google. "
                            "Please sign in with Google."
                        ),
                    ) from None
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        "An account with this email already exists. "
                        "Please sign in with your password."
                    ),
                ) from None

            if concurrent_user.otp_locked_until and _to_utc(concurrent_user.otp_locked_until) > now:
                return MessageResponse(message=generic_message)

            if concurrent_user.otp_last_sent_at:
                elapsed = (now - _to_utc(concurrent_user.otp_last_sent_at)).total_seconds()
                if elapsed < settings.RESEND_COOLDOWN_SECONDS:
                    return MessageResponse(message=generic_message)

            if data.full_name is not None:
                concurrent_user.full_name = data.full_name
            concurrent_user.credential_version += 1
            await db.flush()
            try:
                _, outbox_id = await AuthService._create_and_send_verification_token(
                    db, concurrent_user, pending_password_hash=pwd_hash
                )
                await db.commit()
                dispatch_outbox_delivery(outbox_id)
            except Exception as e:
                logger.error("Failed to create challenge on concurrent re-registration: %s", e)
                await db.commit()

            return MessageResponse(message=generic_message)

        try:
            _, outbox_id = await AuthService._create_and_send_verification_token(
                db, new_user, pending_password_hash=pwd_hash
            )
            await db.commit()
            dispatch_outbox_delivery(outbox_id)
        except Exception as e:
            logger.error("Failed to create verification challenge for new user: %s", e)
            await db.commit()

        return MessageResponse(message=generic_message)

    @staticmethod
    async def authenticate_local(
        db: AsyncSession,
        email: str,
        password: str,
    ) -> User:
        """Authenticate credentials using constant-time verification without enumeration leaks."""
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()

        # Finding 4: Constant-time check without leaking provider or account presence
        target_hash = (
            user.hashed_password
            if (user is not None and user.hashed_password is not None)
            else None
        )
        is_valid = verify_password(password, target_hash)

        if not user or not target_hash or not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password.",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled. Please contact support.",
            )

        return user

    @staticmethod
    async def create_user_session(
        db: AsyncSession,
        user_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[str, str, datetime]:
        """Create a new database-backed session token.

        Returns (raw_session_token, token_hash, expires_at).
        """
        raw_token, token_hash = generate_session_token()
        expires_at = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        user = await db.get(User, user_id)
        credential_version = user.credential_version if user else 1

        session = UserSession(
            id=uuid.uuid4(),
            user_id=user_id,
            token_hash=token_hash,
            credential_version=credential_version,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else None,
        )
        db.add(session)
        await db.commit()
        return raw_token, token_hash, expires_at

    @staticmethod
    async def revoke_session_by_hash(
        db: AsyncSession,
        token_hash: str,
    ) -> None:
        """Revoke a single active session."""
        await db.execute(
            update(UserSession)
            .where(
                UserSession.token_hash == token_hash,
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        await db.commit()

    @staticmethod
    async def revoke_all_user_sessions(
        db: AsyncSession,
        user_id: uuid.UUID,
    ) -> None:
        """Revoke all active sessions for a user across all devices."""
        await db.execute(
            update(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
        await db.commit()

    @staticmethod
    async def verify_email_token(
        db: AsyncSession,
        raw_token: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[User, str, str, int]:
        """Validate single-use verification token, activate credentials, and establish session.

        Uses consistent lock ordering (User before UserToken) to prevent deadlocks.
        """
        try:
            payload = decode_signed_token(raw_token, "verify_email")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification link is invalid or expired.",
            ) from None

        user_id = uuid.UUID(payload["sub"])
        token_hash = hash_token(raw_token)
        now = datetime.now(UTC)

        # 1. Lock user row FIRST to ensure consistent lock ordering across transactions
        user_result = await db.execute(select(User).where(User.id == user_id).with_for_update())
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User account not found.",
            )

        # Recheck user state after acquiring lock
        if user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account is already verified. Please sign in.",
            )

        # 2. Lock token row SECOND
        token_stmt = (
            select(UserToken)
            .where(
                UserToken.user_id == user.id,
                UserToken.token_hash == token_hash,
                UserToken.token_type == "verify_email",
            )
            .with_for_update()
        )
        token_result = await db.execute(token_stmt)
        db_token = token_result.scalar_one_or_none()

        if not db_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification token not found or already processed.",
            )
        if db_token.consumed_at is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This verification link has already been used.",
            )
        if _to_utc(db_token.expires_at) <= now:
            db_token.consumed_at = now
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This verification link has expired. Please request a new one.",
            )

        # Mark token consumed
        db_token.consumed_at = now

        # Finding 1 & 3: Activate credentials bound to this specific challenge
        if db_token.pending_password_hash:
            user.hashed_password = db_token.pending_password_hash

        # Mark user verified and reset persistent attempt budget
        user.is_verified = True
        user.otp_failed_attempts = 0
        user.otp_locked_until = None
        user.credential_version += 1

        # Finding 2: Invalidate sibling verification methods (verify_otp)
        await db.execute(
            update(UserToken)
            .where(
                UserToken.user_id == user.id,
                UserToken.token_type.in_(["verify_email", "verify_otp"]),
                UserToken.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )

        # Create session so email verification automatically signs the user in
        raw_session_token, session_hash = generate_session_token()
        session_expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        session = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=session_hash,
            credential_version=user.credential_version,
            expires_at=session_expires,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else None,
        )
        db.add(session)
        await db.commit()

        csrf_token = generate_csrf_token()
        max_age_seconds = int((session_expires - now).total_seconds())
        return user, raw_session_token, csrf_token, max_age_seconds

    @staticmethod
    async def verify_otp(
        db: AsyncSession,
        email: str,
        otp: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[User, str, str, int]:
        """Validate OTP with persistent attempt budget, activate credentials, and create session."""
        now = datetime.now(UTC)

        # 1. Lock user row consistently FIRST
        user_result = await db.execute(select(User).where(User.email == email).with_for_update())
        user = user_result.scalar_one_or_none()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code or email.",
            )

        # Recheck state after locking
        if user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account is already verified. Please sign in.",
            )

        # P1: Check persistent account-level lockout
        if user.otp_locked_until and _to_utc(user.otp_locked_until) > now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many failed attempts. Account verification is locked.",
            )

        if user.otp_failed_attempts >= settings.MAX_OTP_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many failed attempts. Code locked. Please request a new one.",
            )

        # 2. Lock active unconsumed OTP challenge SECOND
        token_res = await db.execute(
            select(UserToken)
            .where(
                UserToken.user_id == user.id,
                UserToken.token_type == "verify_otp",
                UserToken.consumed_at.is_(None),
            )
            .order_by(UserToken.created_at.desc())
            .with_for_update()
        )
        db_token = token_res.scalar_one_or_none()
        if not db_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active verification code found. Please request a new one.",
            )

        # Check expiration
        exp_at = _to_utc(db_token.expires_at)
        if exp_at <= now:
            db_token.consumed_at = now
            await db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This verification code has expired. Please request a new one.",
            )

        expected_hash = hash_token(f"{user.id}:{otp}")
        if not secrets.compare_digest(db_token.token_hash, expected_hash):
            # P1: Persistent account-level attempt budget increment
            user.otp_failed_attempts += 1
            db_token.attempts += 1
            attempts_left = max(0, settings.MAX_OTP_ATTEMPTS - user.otp_failed_attempts)
            if attempts_left == 0:
                user.otp_locked_until = now + timedelta(minutes=15)
                db_token.consumed_at = now
            await db.commit()
            if attempts_left == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Too many failed attempts. This verification code has been locked.",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid verification code. {attempts_left} attempt(s) remaining.",
            )

        # OTP Matches! Consume challenge atomically
        db_token.consumed_at = now

        # Finding 1 & 3: Activate credentials bound to this specific challenge
        if db_token.pending_password_hash:
            user.hashed_password = db_token.pending_password_hash

        # Mark user verified and reset persistent attempt budget
        user.is_verified = True
        user.otp_failed_attempts = 0
        user.otp_locked_until = None
        user.credential_version += 1

        # Finding 2: Invalidate sibling verification methods (verify_email link)
        await db.execute(
            update(UserToken)
            .where(
                UserToken.user_id == user.id,
                UserToken.token_type.in_(["verify_email", "verify_otp"]),
                UserToken.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )

        # Create session
        raw_session_token, session_hash = generate_session_token()
        session_expires = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        session = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=session_hash,
            credential_version=user.credential_version,
            expires_at=session_expires,
            ip_address=ip_address,
            user_agent=user_agent[:500] if user_agent else None,
        )
        db.add(session)
        await db.commit()

        csrf_token = generate_csrf_token()
        max_age_seconds = int((session_expires - now).total_seconds())
        return user, raw_session_token, csrf_token, max_age_seconds

    @staticmethod
    async def resend_otp(
        db: AsyncSession,
        email: str,
    ) -> MessageResponse:
        """Resend 6-digit OTP with safe cooldown, persistent budget, and anti-enumeration."""
        now = datetime.now(UTC)
        generic_response = (
            "If an eligible unverified account exists for this email, "
            "a new verification code has been sent."
        )

        result = await db.execute(select(User).where(User.email == email).with_for_update())
        user = result.scalar_one_or_none()

        # Finding 2: Never send enrollment OTPs to verified users
        if not user or user.is_verified or not user.is_active:
            return MessageResponse(message=generic_response)

        # P1: Check account-level lockout
        if user.otp_locked_until and _to_utc(user.otp_locked_until) > now:
            remaining_lock = int((_to_utc(user.otp_locked_until) - now).total_seconds())
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Verification attempts locked. Please try again in {remaining_lock} second(s)."
                ),
            )

        # P1: Safe resend cooldown enforced on user.otp_last_sent_at
        if user.otp_last_sent_at:
            last_sent = _to_utc(user.otp_last_sent_at)
            elapsed = (now - last_sent).total_seconds()
            if elapsed < settings.RESEND_COOLDOWN_SECONDS:
                remaining = int(settings.RESEND_COOLDOWN_SECONDS - elapsed)
                msg = f"Please wait {remaining} second(s) before requesting a new code."
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=msg,
                )

        try:
            # P2: Preserve challenge-bound pending password hash across resends
            pending_hash = await AuthService._get_pending_password_hash(db, user)
            _, outbox_id = await AuthService._create_and_send_verification_token(
                db, user, pending_password_hash=pending_hash
            )
            await db.commit()
            dispatch_outbox_delivery(outbox_id)
        except Exception as e:
            logger.error("Failed to resend verification OTP: %s", e)
            await db.commit()

        return MessageResponse(message=generic_response)

    @staticmethod
    async def resend_verification_email(
        db: AsyncSession,
        email: str,
    ) -> str:
        """Resend verification email to unverified accounts."""
        now = datetime.now(UTC)
        result = await db.execute(select(User).where(User.email == email).with_for_update())
        user = result.scalar_one_or_none()

        generic_response = (
            "If this account exists and is unverified, a new verification link has been sent."
        )

        if user and not user.is_verified and user.is_active:
            if user.otp_locked_until and _to_utc(user.otp_locked_until) > now:
                return generic_response

            if user.otp_last_sent_at:
                elapsed = (now - _to_utc(user.otp_last_sent_at)).total_seconds()
                if elapsed < settings.RESEND_COOLDOWN_SECONDS:
                    return generic_response

            try:
                pending_hash = await AuthService._get_pending_password_hash(db, user)
                _, outbox_id = await AuthService._create_and_send_verification_token(
                    db, user, pending_password_hash=pending_hash
                )
                await db.commit()
                dispatch_outbox_delivery(outbox_id)
            except Exception as e:
                logger.error("Failed to resend verification email: %s", e)
                await db.commit()

        return generic_response

    @staticmethod
    async def request_password_reset(
        db: AsyncSession,
        email: str,
    ) -> str:
        """Generate a 15-minute password reset token and enqueue in outbox."""
        now = datetime.now(UTC)
        result = await db.execute(select(User).where(User.email == email).with_for_update())
        user = result.scalar_one_or_none()

        generic_message = (
            "If an account exists with that email address, password reset "
            "instructions have been sent."
        )

        if not user or not user.is_active:
            return generic_message

        # Invalidate pending signup/verification challenges AND old reset tokens
        await db.execute(
            update(UserToken)
            .where(
                UserToken.user_id == user.id,
                UserToken.token_type.in_(["verify_otp", "verify_email", "reset_password"]),
                UserToken.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )

        if not user.hashed_password:
            await db.commit()
            return generic_message

        raw_jwt, token_hash, expires_at = create_signed_token(
            user_id=user.id,
            token_type="reset_password",
            expires_delta=timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
        )

        db_token = UserToken(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            token_type="reset_password",
            expires_at=expires_at,
            last_sent_at=now,
        )
        db.add(db_token)
        outbox_item = enqueue_password_reset_outbox(db, user.email, raw_jwt)
        await db.commit()
        dispatch_password_reset_email_background(user.email, raw_jwt)
        dispatch_outbox_delivery(outbox_item.id)
        return generic_message

    @staticmethod
    async def reset_password(
        db: AsyncSession,
        raw_token: str,
        new_password: str,
    ) -> None:
        """Reset password using single-use token and revoke all existing sessions."""
        try:
            decode_signed_token(raw_token, "reset_password")
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Password reset link is invalid or expired.",
            ) from None

        token_hash = hash_token(raw_token)
        now = datetime.now(UTC)

        # Finding 3: Atomic token consumption with conditional UPDATE ... RETURNING
        token_stmt = (
            update(UserToken)
            .where(
                UserToken.token_hash == token_hash,
                UserToken.token_type == "reset_password",
                UserToken.consumed_at.is_(None),
                UserToken.expires_at > now,
            )
            .values(consumed_at=now)
            .returning(UserToken.id, UserToken.user_id)
        )
        token_result = await db.execute(token_stmt)
        consumed_token = token_result.first()

        if not consumed_token:
            check = await db.execute(
                select(UserToken).where(
                    UserToken.token_hash == token_hash,
                    UserToken.token_type == "reset_password",
                )
            )
            existing = check.scalar_one_or_none()
            if not existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Reset token not found or already consumed.",
                )
            if existing.consumed_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This reset token has already been used.",
                )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This reset token has expired. Please request a new one.",
            )

        # Finding 4: Row lock with with_for_update() and credential_version increment
        user_result = await db.execute(
            select(User).where(User.id == consumed_token.user_id).with_for_update()
        )
        user = user_result.scalar_one_or_none()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Account is invalid or inactive.",
            )

        # Finding 2: Invalidate all existing tokens on password reset
        await db.execute(
            update(UserToken)
            .where(
                UserToken.user_id == user.id,
                UserToken.token_type.in_(["verify_otp", "verify_email", "reset_password"]),
                UserToken.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )

        user.hashed_password = hash_password(new_password)
        user.credential_version += 1

        # Invalidate all existing sessions on password reset in same transaction
        await db.execute(
            update(UserSession)
            .where(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        await db.commit()

    @staticmethod
    async def handle_google_user(
        db: AsyncSession,
        google_profile: dict[str, str | None],
    ) -> User:
        """Process verified Google OpenID Connect profile with safe account linking."""
        google_id = str(google_profile["google_id"])
        email = str(google_profile["email"]).strip().lower()
        full_name = google_profile.get("full_name")

        # 1. Match by google_id
        res_gid = await db.execute(select(User).where(User.google_id == google_id))
        user_by_gid = res_gid.scalar_one_or_none()
        if user_by_gid:
            if not user_by_gid.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is disabled.",
                )
            return user_by_gid

        # 2. Match by email
        res_email = await db.execute(select(User).where(User.email == email))
        user_by_email = res_email.scalar_one_or_none()

        if user_by_email:
            if not user_by_email.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is disabled.",
                )
            # Conflicting Google ID check
            if user_by_email.google_id and user_by_email.google_id != google_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Account is linked to a different Google account.",
                )
            # Safe automatic linking: Google OIDC verified email links Google ID seamlessly
            if user_by_email.google_id is None:
                user_by_email.google_id = google_id
                user_by_email.is_verified = True
                if full_name and not user_by_email.full_name:
                    user_by_email.full_name = full_name
                await db.commit()
            return user_by_email

        # 3. Create fresh Google user (OIDC verified email is automatically marked verified)
        new_user = User(
            id=uuid.uuid4(),
            email=email,
            hashed_password=None,
            full_name=full_name,
            is_active=True,
            is_verified=True,  # Google verifies email ownership
            role="user",
            auth_provider="google",
            google_id=google_id,
        )
        db.add(new_user)
        await db.commit()
        return new_user
