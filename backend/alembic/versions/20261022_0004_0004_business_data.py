"""add tenant accounts and synthetic business data tables

Revision ID: 0004_business_data
Revises: 0003_outbox_otp_budget
Create Date: 2026-10-22 16:45:00.000000

Additive only: creates accounts, customers, invoices, payments and adds a nullable
users.account_id column. Existing authentication rows are untouched.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004_business_data"
down_revision: str | None = "0003_outbox_otp_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("is_demo", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.add_column("users", sa.Column("account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_users_account_id",
        "users",
        "accounts",
        ["account_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_account_id", "users", ["account_id"])

    op.create_table(
        "customers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("external_ref", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("industry", sa.String(length=100), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=False),
        sa.Column("segment", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "external_ref", name="uq_customers_account_ref"),
        sa.UniqueConstraint("account_id", "id", name="uq_customers_account_id_id"),
    )
    op.create_index("ix_customers_account_id", "customers", ["account_id"])

    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_number", sa.String(length=32), nullable=False),
        sa.Column("issue_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("subtotal_cents", sa.BigInteger(), nullable=False),
        sa.Column("tax_cents", sa.BigInteger(), nullable=False),
        sa.Column("total_cents", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["account_id", "customer_id"],
            ["customers.account_id", "customers.id"],
            name="fk_invoices_account_customer",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "invoice_number", name="uq_invoices_account_number"),
        sa.UniqueConstraint("account_id", "id", name="uq_invoices_account_id_id"),
        sa.CheckConstraint("subtotal_cents >= 0", name="ck_invoices_subtotal_nonneg"),
        sa.CheckConstraint("tax_cents >= 0", name="ck_invoices_tax_nonneg"),
        sa.CheckConstraint("total_cents = subtotal_cents + tax_cents", name="ck_invoices_total"),
        sa.CheckConstraint("due_date >= issue_date", name="ck_invoices_due_after_issue"),
        sa.CheckConstraint("status IN ('open', 'paid', 'void')", name="ck_invoices_status"),
        sa.CheckConstraint("length(currency) = 3", name="ck_invoices_currency"),
    )
    op.create_index("ix_invoices_account_issue_date", "invoices", ["account_id", "issue_date"])
    op.create_index(
        "ix_invoices_account_status_due", "invoices", ["account_id", "status", "due_date"]
    )
    op.create_index("ix_invoices_account_customer", "invoices", ["account_id", "customer_id"])

    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["account_id", "invoice_id"],
            ["invoices.account_id", "invoices.id"],
            name="fk_payments_account_invoice",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("amount_cents > 0", name="ck_payments_amount_positive"),
        sa.CheckConstraint(
            "method IN ('bank_transfer', 'card', 'ach', 'check')", name="ck_payments_method"
        ),
    )
    op.create_index("ix_payments_account_paid_on", "payments", ["account_id", "paid_on"])
    op.create_index("ix_payments_account_invoice", "payments", ["account_id", "invoice_id"])


def downgrade() -> None:
    # Drops only business-data objects; authentication tables and rows are preserved.
    op.drop_index("ix_payments_account_invoice", table_name="payments")
    op.drop_index("ix_payments_account_paid_on", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_invoices_account_customer", table_name="invoices")
    op.drop_index("ix_invoices_account_status_due", table_name="invoices")
    op.drop_index("ix_invoices_account_issue_date", table_name="invoices")
    op.drop_table("invoices")
    op.drop_index("ix_customers_account_id", table_name="customers")
    op.drop_table("customers")
    op.drop_index("ix_users_account_id", table_name="users")
    op.drop_constraint("fk_users_account_id", "users", type_="foreignkey")
    op.drop_column("users", "account_id")
    op.drop_table("accounts")
