"""Cryptographic and token security utilities for Orvian authentication."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.config import get_settings

settings = get_settings()

# Initialize Argon2id password hasher
_password_hash = PasswordHash((Argon2Hasher(),))

# Dummy hash for timing attack mitigation during user-not-found login attempts
_DUMMY_HASH = _password_hash.hash("dummy-password-timing-mitigation")

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "orvian"
JWT_AUDIENCE = "orvian-auth"


def hash_password(password: str) -> str:
    """Hash a plaintext password using Argon2id."""
    return _password_hash.hash(password)


def verify_password(password: str, hashed_password: str | None) -> bool:
    """Verify password against Argon2id hash with constant-time mitigation.

    If hashed_password is None, a dummy hash is verified to prevent timing
    side-channel attacks that enable account enumeration.
    """
    if hashed_password is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, hashed_password)


def generate_session_token() -> tuple[str, str]:
    """Generate a high-entropy session token and its SHA-256 hash.

    Returns:
        (raw_token, token_hash): raw_token is sent to client; token_hash is stored in DB.
    """
    raw_token = secrets.token_urlsafe(32)
    token_hash = hash_token(raw_token)
    return raw_token, token_hash


def hash_token(token: str) -> str:
    """Compute SHA-256 hex digest of a token string."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_csrf_token() -> str:
    """Generate a cryptographically secure CSRF token."""
    return secrets.token_urlsafe(32)


def create_signed_token(
    user_id: uuid.UUID,
    token_type: str,
    expires_delta: timedelta,
) -> tuple[str, str, datetime]:
    """Create a signed JWT token and its SHA-256 hash for single-use verification/reset.

    Returns:
        (raw_jwt, token_hash, expires_at): raw_jwt sent to user; token_hash stored in DB.
    """
    now = datetime.now(UTC)
    expires_at = now + expires_delta
    token_jti = str(uuid.uuid4())

    payload = {
        "sub": str(user_id),
        "type": token_type,
        "jti": token_jti,
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "exp": expires_at,
    }

    raw_jwt = jwt.encode(payload, settings.AUTH_SECRET_KEY, algorithm=JWT_ALGORITHM)
    token_hash = hash_token(raw_jwt)
    return raw_jwt, token_hash, expires_at


def generate_numeric_otp(
    user_id: uuid.UUID,
    length: int = 6,
) -> tuple[str, str, datetime]:
    """Generate a cryptographically secure numeric OTP and its salted SHA-256 hash.

    Returns:
        (otp_code, token_hash, expires_at): otp_code sent to user; token_hash stored in DB.
    """
    code = f"{secrets.randbelow(10**length):0{length}d}"
    token_hash = hash_token(f"{user_id}:{code}")
    now = datetime.now(UTC)
    expires_at = now + timedelta(minutes=settings.EMAIL_VERIFICATION_OTP_EXPIRE_MINUTES)
    return code, token_hash, expires_at


def decode_signed_token(raw_token: str, expected_type: str) -> dict[str, Any]:
    """Decode and validate a signed JWT token.

    Raises:
        jwt.PyJWTError: If the token is invalid, expired, or has mismatched claims.
        ValueError: If token_type does not match expected_type.
    """
    payload = jwt.decode(
        raw_token,
        settings.AUTH_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
        issuer=JWT_ISSUER,
        audience=JWT_AUDIENCE,
    )
    if payload.get("type") != expected_type:
        raise ValueError(
            f"Invalid token type: expected '{expected_type}', got '{payload.get('type')}'"
        )
    return payload
