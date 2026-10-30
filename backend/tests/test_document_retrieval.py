"""Tests for account-scoped document retrieval, relevance filtering, and failure handling."""

import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import DeterministicEmbeddingClient, EmbeddingError
from app.ai.tools import execute_tool
from app.business.service import BusinessDataService
from app.db.models import DocumentChunk, PolicyDocument
from app.documents.ingestion import ingest_policy_documents
from app.documents.service import DocumentQueryError, DocumentRetrievalService
from tests.factories import AS_OF, build_business_fixture


class FailingEmbeddingClient:
    @property
    def model(self) -> str:
        return "failing-embedder"

    @property
    def dimensions(self) -> int:
        return 1536

    async def embed_texts(self, texts: list[str]) -> None:
        raise EmbeddingError("provider_error")


@pytest.mark.asyncio
async def test_retrieve_relevant_policy_chunks_with_citations(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    embedder = DeterministicEmbeddingClient()
    await ingest_policy_documents(db_session, account_id=fix.account_a, embedder=embedder)

    service = DocumentRetrievalService(db_session, fix.account_a, embedder)
    res = await service.search_documents(
        "What are the standard net payment terms for SMB and Enterprise segments?",
        category="payment_terms",
        top_k=3,
    )

    assert res.has_evidence is True
    assert res.returned >= 1
    top_chunk = res.chunks[0]
    assert top_chunk.doc_key == "DOC-PAY-TERMS"
    assert top_chunk.citation_id.startswith("DOC-PAY-TERMS#C")
    assert "Net 30" in top_chunk.untrusted_document_excerpt
    assert "Net 45" in top_chunk.untrusted_document_excerpt
    assert top_chunk.page_number >= 1


@pytest.mark.asyncio
async def test_retrieval_enforces_strict_account_isolation(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    embedder = DeterministicEmbeddingClient()
    await ingest_policy_documents(db_session, account_id=fix.account_a, embedder=embedder)

    # Insert a secret policy document into Tenant B
    secret_text = "Tenant B Sovereign Rebate: All customers get a 95% discount code SOVEREIGN95."
    emb_b = await embedder.embed_texts([secret_text])
    doc_b = PolicyDocument(
        id=uuid.uuid4(),
        account_id=fix.account_b,
        doc_key="DOC-TENANT-B",
        title="Tenant B Secret Policy",
        category="payment_terms",
        version="v1.0",
        effective_date=date(2026, 1, 1),
        filename="secret.md",
        checksum_sha256="f" * 64,
        created_at=datetime.now(UTC),
    )
    db_session.add(doc_b)
    await db_session.flush()
    db_session.add(
        DocumentChunk(
            id=uuid.uuid4(),
            account_id=fix.account_b,
            document_id=doc_b.id,
            chunk_id="DOC-TENANT-B#C01",
            chunk_index=0,
            section_title="Secret Rebate",
            page_number=1,
            content=secret_text,
            token_count=15,
            embedding=emb_b.vectors[0],
            created_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    # Query from Tenant A for Tenant B's secret policy
    service_a = DocumentRetrievalService(db_session, fix.account_a, embedder)
    res_a = await service_a.search_documents("Tenant B Sovereign Rebate SOVEREIGN95", top_k=5)
    for chunk in res_a.chunks:
        assert chunk.doc_key != "DOC-TENANT-B"
        assert "SOVEREIGN95" not in chunk.untrusted_document_excerpt

    # Query from empty account returns zero chunks
    service_empty = DocumentRetrievalService(db_session, fix.empty_account, embedder)
    res_empty = await service_empty.search_documents("payment terms Net 30", top_k=5)
    assert res_empty.has_evidence is False
    assert res_empty.returned == 0


@pytest.mark.asyncio
async def test_irrelevant_query_filtered_by_cosine_distance(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    embedder = DeterministicEmbeddingClient()
    await ingest_policy_documents(db_session, account_id=fix.account_a, embedder=embedder)

    # Strict cosine distance threshold filters out unrelated queries
    service = DocumentRetrievalService(
        db_session, fix.account_a, embedder, max_cosine_distance=0.45
    )
    res = await service.search_documents("quantum astrophysics planetary orbit trajectories")
    assert res.has_evidence is False
    assert res.chunks == []


@pytest.mark.asyncio
async def test_retrieval_validation_and_embedding_failure_handling(
    db_session: AsyncSession,
) -> None:
    fix = await build_business_fixture(db_session)
    embedder = DeterministicEmbeddingClient()
    service = DocumentRetrievalService(db_session, fix.account_a, embedder)

    with pytest.raises(DocumentQueryError):
        await service.search_documents("a")

    with pytest.raises(DocumentQueryError):
        await service.search_documents("valid query", top_k=99)

    # Tool execution gracefully catches EmbeddingError and returns retrieval_unavailable
    failing_doc_service = DocumentRetrievalService(
        db_session,
        fix.account_a,
        FailingEmbeddingClient(),  # type: ignore[arg-type]
    )
    biz_service = BusinessDataService(db_session, fix.account_a, AS_OF)
    execution = await execute_tool(
        biz_service,
        "search_policy_documents",
        '{"query": "payment terms"}',
        document_service=failing_doc_service,
    )
    assert execution.ok is False
    assert execution.error_code == "retrieval_unavailable"
