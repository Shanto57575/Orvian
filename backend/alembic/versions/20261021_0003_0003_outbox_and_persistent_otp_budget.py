"""add transactional email outbox and persistent account otp budget

Revision ID: 0003_outbox_otp_budget
Revises: 0002_otp_challenge
Create Date: 2026-10-21 23:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_outbox_otp_budget"
down_revision: str | None = "0002_otp_challenge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add persistent OTP attempt budget & cooldown columns to users
    op.add_column(
        "users",
        sa.Column(
            "otp_failed_attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("otp_locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("otp_last_sent_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2. Create transactional email outbox table
    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "max_retries",
            sa.Integer(),
            server_default=sa.text("3"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_email_outbox_recipient", "email_outbox", ["recipient"])
    op.create_index("ix_email_outbox_status", "email_outbox", ["status"])


def downgrade() -> None:
    op.drop_index("ix_email_outbox_status", table_name="email_outbox")
    op.drop_index("ix_email_outbox_recipient", table_name="email_outbox")
    op.drop_table("email_outbox")
    op.drop_column("users", "otp_last_sent_at")
    op.drop_column("users", "otp_locked_until")
    op.drop_column("users", "otp_failed_attempts")
