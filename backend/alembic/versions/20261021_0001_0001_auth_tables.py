"""create auth tables

Revision ID: 0001_auth_tables
Revises:
Create Date: 2026-10-21 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_auth_tables"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "is_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(length=50),
            server_default="user",
            nullable=False,
        ),
        sa.Column(
            "auth_provider",
            sa.String(length=50),
            server_default="local",
            nullable=False,
        ),
        sa.Column(
            "credential_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("google_id", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_index(op.f("ix_users_google_id"), "users", ["google_id"], unique=True)
    op.create_index(op.f("ix_users_role"), "users", ["role"], unique=False)

    # Create user_sessions table
    op.create_table(
        "user_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "credential_version",
            sa.Integer(),
            server_default=sa.text("1"),
            nullable=False,
        ),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_user_sessions_user_id"),
        "user_sessions",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_sessions_token_hash"),
        "user_sessions",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_user_sessions_expires_at"),
        "user_sessions",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_sessions_revoked_at"),
        "user_sessions",
        ["revoked_at"],
        unique=False,
    )

    # Create user_tokens table
    op.create_table(
        "user_tokens",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_type", sa.String(length=50), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_user_tokens_user_id"),
        "user_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_tokens_token_hash"),
        "user_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        op.f("ix_user_tokens_token_type"),
        "user_tokens",
        ["token_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_tokens_expires_at"),
        "user_tokens",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_tokens_consumed_at"),
        "user_tokens",
        ["consumed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("user_tokens")
    op.drop_table("user_sessions")
    op.drop_table("users")
