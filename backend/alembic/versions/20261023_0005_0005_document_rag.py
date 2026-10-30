"""add tenant policy_documents and document_chunks with pgvector HNSW index

Revision ID: 0005_document_rag
Revises: 0004_business_data
Create Date: 2026-10-23 13:30:00.000000

Additive only: enables pgvector extension, creates policy_documents and document_chunks
tables, and builds an HNSW cosine index over document_chunks.embedding.
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_document_rag"
down_revision: str | None = "0004_business_data"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "policy_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("doc_key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("version", sa.String(length=20), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("filename", sa.String(length=120), nullable=False),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "doc_key", name="uq_policy_docs_account_key"),
        sa.UniqueConstraint("account_id", "id", name="uq_policy_docs_account_id_id"),
        sa.CheckConstraint(
            "category IN ('payment_terms', 'collections', 'refunds', "
            "'credit_policy', 'operating_procedures')",
            name="ck_policy_docs_category",
        ),
    )
    op.create_index("ix_policy_documents_account_id", "policy_documents", ["account_id"])
    op.create_index(
        "ix_policy_docs_account_category", "policy_documents", ["account_id", "category"]
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_id", sa.String(length=80), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section_title", sa.String(length=200), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("embedding", pgvector.sqlalchemy.Vector(1536), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["account_id", "document_id"],
            ["policy_documents.account_id", "policy_documents.id"],
            name="fk_doc_chunks_account_document",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "chunk_id", name="uq_doc_chunks_account_chunk_id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_doc_chunks_doc_idx"),
        sa.CheckConstraint("chunk_index >= 0", name="ck_doc_chunks_index_nonneg"),
        sa.CheckConstraint("page_number >= 1", name="ck_doc_chunks_page_pos"),
        sa.CheckConstraint("token_count > 0", name="ck_doc_chunks_tokens_pos"),
    )
    op.create_index("ix_doc_chunks_account_doc", "document_chunks", ["account_id", "document_id"])

    if bind.dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_doc_chunks_embedding_hnsw "
            "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS ix_doc_chunks_embedding_hnsw")
    op.drop_index("ix_doc_chunks_account_doc", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_policy_docs_account_category", table_name="policy_documents")
    op.drop_index("ix_policy_documents_account_id", table_name="policy_documents")
    op.drop_table("policy_documents")
