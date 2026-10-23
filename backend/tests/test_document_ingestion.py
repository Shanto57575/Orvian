"""Tests for policy markdown parsing, chunking, and idempotent account-scoped ingestion."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import DeterministicEmbeddingClient
from app.db.models import DocumentChunk, PolicyDocument
from app.documents.chunker import (
    DocumentParseError,
    load_policy_corpus,
    parse_policy_markdown,
)
from app.documents.ingestion import DEFAULT_POLICIES_DIR, ingest_policy_documents
from tests.factories import build_business_fixture


def test_load_default_policy_corpus() -> None:
    corpus = load_policy_corpus(DEFAULT_POLICIES_DIR)
    assert len(corpus) == 5
    keys = [doc.doc_key for doc in corpus]
    assert keys == [
        "DOC-PAY-TERMS",
        "DOC-COLLECTIONS",
        "DOC-REFUNDS",
        "DOC-CREDIT",
        "DOC-OPS-SOP",
    ]
    for doc in corpus:
        assert len(doc.chunks) >= 3
        for idx, chunk in enumerate(doc.chunks):
            assert chunk.chunk_index == idx
            assert chunk.chunk_id == f"{doc.doc_key}#C{idx + 1:02d}"
            assert chunk.page_number >= 1
            assert chunk.token_count > 0
            assert doc.title in chunk.content


def test_parse_policy_markdown_rejects_invalid_frontmatter() -> None:
    with pytest.raises(DocumentParseError, match="missing YAML frontmatter"):
        parse_policy_markdown("## Section 1\nHello world", "bad.md")

    invalid_cat = (
        "---\n"
        "doc_key: DOC-BAD\n"
        "title: Bad Doc\n"
        "category: unknown_category\n"
        "version: v1.0\n"
        "effective_date: 2026-01-01\n"
        "---\n"
        "## Section 1\nBody"
    )
    with pytest.raises(DocumentParseError, match="invalid category"):
        parse_policy_markdown(invalid_cat, "bad_cat.md")


@pytest.mark.asyncio
async def test_ingest_policy_documents_is_idempotent(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    embedder = DeterministicEmbeddingClient()

    # First run: all 5 documents inserted
    first = await ingest_policy_documents(db_session, account_id=fix.account_a, embedder=embedder)
    await db_session.commit()

    assert first.documents_processed == 5
    assert first.documents_updated == 5
    assert first.documents_skipped == 0
    assert first.chunks_written >= 15
    assert first.embedding_tokens > 0

    # Second run without changes: all 5 documents skipped (zero embedding calls)
    second = await ingest_policy_documents(db_session, account_id=fix.account_a, embedder=embedder)
    await db_session.commit()

    assert second.documents_processed == 5
    assert second.documents_updated == 0
    assert second.documents_skipped == 5
    assert second.chunks_written == 0
    assert second.embedding_tokens == 0

    # Force re-run: all 5 updated in place without duplicating rows
    third = await ingest_policy_documents(
        db_session, account_id=fix.account_a, embedder=embedder, force=True
    )
    await db_session.commit()

    assert third.documents_updated == 5
    assert third.chunks_written == first.chunks_written

    doc_count = (
        await db_session.execute(
            select(func.count(PolicyDocument.id)).where(PolicyDocument.account_id == fix.account_a)
        )
    ).scalar_one()
    chunk_count = (
        await db_session.execute(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.account_id == fix.account_a)
        )
    ).scalar_one()
    assert doc_count == 5
    assert chunk_count == first.chunks_written
