"""add otp and challenge binding columns to user_tokens

Revision ID: 0002_otp_challenge
Revises: 0001_auth_tables
Create Date: 2026-10-21 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_otp_challenge"
down_revision: str | None = "0001_auth_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_tokens",
        sa.Column("pending_password_hash", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "user_tokens",
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "user_tokens",
        sa.Column(
            "max_attempts",
            sa.Integer(),
            server_default=sa.text("5"),
            nullable=False,
        ),
    )
    op.add_column(
        "user_tokens",
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_tokens", "last_sent_at")
    op.drop_column("user_tokens", "max_attempts")
    op.drop_column("user_tokens", "attempts")
    op.drop_column("user_tokens", "pending_password_hash")
