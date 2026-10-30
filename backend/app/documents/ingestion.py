"""Idempotent, account-scoped document ingestion pipeline."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import EmbeddingClient
from app.config import BACKEND_DIR
from app.db.models import DocumentChunk, PolicyDocument
from app.documents.chunker import load_policy_corpus
from app.documents.schemas import ParsedPolicyDocument

DEFAULT_POLICIES_DIR = BACKEND_DIR / "data" / "policies"
_DOC_UUID_NAMESPACE = uuid.UUID("91f8b7a4-5c31-489a-8a2b-7e1155c92b01")


@dataclass(frozen=True)
class IngestionSummary:
    account_id: uuid.UUID
    documents_processed: int
    documents_updated: int
    documents_skipped: int
    chunks_written: int
    embedding_tokens: int


def deterministic_doc_id(account_id: uuid.UUID, doc_key: str) -> uuid.UUID:
    return uuid.uuid5(_DOC_UUID_NAMESPACE, f"{account_id}:doc:{doc_key}")


def deterministic_chunk_row_id(account_id: uuid.UUID, chunk_id: str) -> uuid.UUID:
    return uuid.uuid5(_DOC_UUID_NAMESPACE, f"{account_id}:chunk:{chunk_id}")


async def ingest_policy_documents(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    embedder: EmbeddingClient,
    documents: Sequence[ParsedPolicyDocument] | None = None,
    policies_dir: Path = DEFAULT_POLICIES_DIR,
    force: bool = False,
) -> IngestionSummary:
    """Ingest parsed policy documents for a single account idempotently.

    If a document with the same `(account_id, doc_key)` already exists and its
    `checksum_sha256` matches (and `force=False`), it is skipped without calling the
    embedding API. Otherwise its metadata and chunks are replaced atomically.
    """
    corpus = list(documents) if documents is not None else load_policy_corpus(policies_dir)

    existing_rows = await session.execute(
        select(PolicyDocument).where(PolicyDocument.account_id == account_id)
    )
    existing_by_key: dict[str, PolicyDocument] = {
        doc.doc_key: doc for doc in existing_rows.scalars().all()
    }

    docs_updated = 0
    docs_skipped = 0
    chunks_written = 0
    total_tokens = 0
    now = datetime.now(UTC)

    for parsed in corpus:
        existing = existing_by_key.get(parsed.doc_key)
        if (
            existing is not None
            and existing.checksum_sha256 == parsed.checksum_sha256
            and not force
        ):
            docs_skipped += 1
            continue

        # Generate embeddings for all chunks of this document in a single batch
        chunk_texts = [c.content for c in parsed.chunks]
        emb_result = await embedder.embed_texts(chunk_texts)
        total_tokens += emb_result.total_tokens

        if existing is not None:
            await session.execute(
                delete(DocumentChunk).where(
                    DocumentChunk.account_id == account_id,
                    DocumentChunk.document_id == existing.id,
                )
            )
            existing.title = parsed.title
            existing.category = parsed.category
            existing.version = parsed.version
            existing.effective_date = parsed.effective_date
            existing.filename = parsed.filename
            existing.checksum_sha256 = parsed.checksum_sha256
            doc_id = existing.id
        else:
            doc_id = deterministic_doc_id(account_id, parsed.doc_key)
            doc_model = PolicyDocument(
                id=doc_id,
                account_id=account_id,
                doc_key=parsed.doc_key,
                title=parsed.title,
                category=parsed.category,
                version=parsed.version,
                effective_date=parsed.effective_date,
                filename=parsed.filename,
                checksum_sha256=parsed.checksum_sha256,
                created_at=now,
            )
            session.add(doc_model)

        await session.flush()

        for parsed_chunk, vector in zip(parsed.chunks, emb_result.vectors, strict=True):
            chunk_row = DocumentChunk(
                id=deterministic_chunk_row_id(account_id, parsed_chunk.chunk_id),
                account_id=account_id,
                document_id=doc_id,
                chunk_id=parsed_chunk.chunk_id,
                chunk_index=parsed_chunk.chunk_index,
                section_title=parsed_chunk.section_title,
                page_number=parsed_chunk.page_number,
                content=parsed_chunk.content,
                token_count=parsed_chunk.token_count,
                embedding=vector,
                created_at=now,
            )
            session.add(chunk_row)
            chunks_written += 1

        docs_updated += 1

    await session.flush()
    return IngestionSummary(
        account_id=account_id,
        documents_processed=len(corpus),
        documents_updated=docs_updated,
        documents_skipped=docs_skipped,
        chunks_written=chunks_written,
        embedding_tokens=total_tokens,
    )
