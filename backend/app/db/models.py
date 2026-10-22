"""SQLAlchemy 2 database models for authentication, sessions, and tenant business data."""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Account(Base):
    """Tenant boundary. Every business record belongs to exactly one account."""

    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class User(Base):
    """User account entity."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="user", nullable=False, index=True)
    auth_provider: Mapped[str] = mapped_column(String(50), default="local", nullable=False)
    credential_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    google_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    otp_failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    otp_locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    otp_last_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Tenant membership: one account per user for now. NULL means no business data access.
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL", name="fk_users_account_id"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )
    tokens: Mapped[list["UserToken"]] = relationship(
        "UserToken", back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base):
    """Active or historical user authentication session."""

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    credential_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="sessions")


class UserToken(Base):
    """Single-use cryptographically hashed token for email verification and password reset."""

    __tablename__ = "user_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    token_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # "verify_email", "reset_password"
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    pending_password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="tokens")


class EmailOutbox(Base):
    """Transactional email outbox table for reliable delivery with bounded retries."""

    __tablename__ = "email_outbox"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body_text: Mapped[str] = mapped_column(String, nullable=False)
    body_html: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )  # "pending", "sent", "failed"
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ====================================================================
# Tenant business data (synthetic demo data only)
# ====================================================================
INVOICE_STATUSES = ("open", "paid", "void")
PAYMENT_METHODS = ("bank_transfer", "card", "ach", "check")


class Customer(Base):
    """Synthetic customer record owned by an account."""

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("account_id", "external_ref", name="uq_customers_account_ref"),
        # Target for composite tenant-safe foreign keys from invoices.
        UniqueConstraint("account_id", "id", name="uq_customers_account_id_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_ref: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    segment: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Invoice(Base):
    """Synthetic invoice. Monetary amounts are integer minor units (cents)."""

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("account_id", "invoice_number", name="uq_invoices_account_number"),
        UniqueConstraint("account_id", "id", name="uq_invoices_account_id_id"),
        ForeignKeyConstraint(
            ["account_id", "customer_id"],
            ["customers.account_id", "customers.id"],
            name="fk_invoices_account_customer",
            ondelete="CASCADE",
        ),
        CheckConstraint("subtotal_cents >= 0", name="ck_invoices_subtotal_nonneg"),
        CheckConstraint("tax_cents >= 0", name="ck_invoices_tax_nonneg"),
        CheckConstraint("total_cents = subtotal_cents + tax_cents", name="ck_invoices_total"),
        CheckConstraint("due_date >= issue_date", name="ck_invoices_due_after_issue"),
        CheckConstraint("status IN ('open', 'paid', 'void')", name="ck_invoices_status"),
        CheckConstraint("length(currency) = 3", name="ck_invoices_currency"),
        Index("ix_invoices_account_issue_date", "account_id", "issue_date"),
        Index("ix_invoices_account_status_due", "account_id", "status", "due_date"),
        Index("ix_invoices_account_customer", "account_id", "customer_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    invoice_number: Mapped[str] = mapped_column(String(32), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    subtotal_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    tax_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Payment(Base):
    """Synthetic payment applied to a single invoice. Amount in integer cents."""

    __tablename__ = "payments"
    __table_args__ = (
        ForeignKeyConstraint(
            ["account_id", "invoice_id"],
            ["invoices.account_id", "invoices.id"],
            name="fk_payments_account_invoice",
            ondelete="CASCADE",
        ),
        CheckConstraint("amount_cents > 0", name="ck_payments_amount_positive"),
        CheckConstraint(
            "method IN ('bank_transfer', 'card', 'ach', 'check')", name="ck_payments_method"
        ),
        Index("ix_payments_account_paid_on", "account_id", "paid_on"),
        Index("ix_payments_account_invoice", "account_id", "invoice_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
