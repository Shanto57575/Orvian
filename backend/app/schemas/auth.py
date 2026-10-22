"""Pydantic v2 schemas for authentication requests, responses, and user profiles."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    """Payload for registering a new local user."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v


class LoginRequest(BaseModel):
    """Payload for local email/password login."""

    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class UserResponse(BaseModel):
    """Public user identity and status schema."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    is_verified: bool
    role: str
    auth_provider: str
    created_at: datetime


class AuthResponse(BaseModel):
    """Authentication response returned upon successful login/registration."""

    user: UserResponse
    message: str
    csrf_token: str


class VerifyEmailRequest(BaseModel):
    """Payload containing email verification token."""

    token: str = Field(min_length=10)


class ResendVerificationRequest(BaseModel):
    """Payload to request resending a verification email."""

    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class ForgotPasswordRequest(BaseModel):
    """Payload to request password reset instructions."""

    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class ResetPasswordRequest(BaseModel):
    """Payload containing token and new password for account recovery."""

    token: str = Field(min_length=10)
    new_password: str = Field(min_length=8, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        return v


class MessageResponse(BaseModel):
    """Generic message response schema."""

    message: str


class RegisterResponse(BaseModel):
    """Registration response containing status, email, and dev OTP for local development."""

    message: str
    email: str
    dev_otp: str | None = None


class VerifyOtpRequest(BaseModel):
    """Payload containing user email and 6-digit verification code."""

    email: EmailStr
    otp: str = Field(min_length=6, max_length=6)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        clean = v.strip()
        if not clean.isdigit() or len(clean) != 6:
            raise ValueError("Verification code must be exactly 6 digits.")
        return clean


class ResendOtpRequest(BaseModel):
    """Payload to request a fresh 6-digit verification OTP."""

    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class SessionResponse(BaseModel):
    """Metadata representing an active user session."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    ip_address: str | None
    user_agent: str | None
    is_current: bool = False
