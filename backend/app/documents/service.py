"""Account-scoped document retrieval service using pgvector + lexical hybrid scoring.

Security invariants:
- ``account_id`` is bound at service construction time from the authenticated user's session.
  AI tools can never supply or override ``account_id``.
- Every SQL query filters ``DocumentChunk.account_id == self._account_id`` and joins
  ``PolicyDocument`` on both ``id`` and ``account_id``.
- Low-similarity candidates above ``max_cosine_distance`` (and without strong domain-keyword
  evidence) are discarded so irrelevant queries return ``has_evidence=False``.
"""

import math
import re
import uuid
from typing import cast

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import EmbeddingClient
from app.db.models import POLICY_CATEGORIES, DocumentChunk, PolicyDocument
from app.documents.schemas import DocumentSearchResult, PolicyCategory, RetrievedChunkItem

MAX_TOP_K = 8
MAX_QUERY_LENGTH = 300
_QUERY_TOKEN_RE = re.compile(r"[a-z0-9_+#.-]+")
_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "are",
        "what",
        "which",
        "how",
        "when",
        "where",
        "who",
        "our",
        "company",
        "policy",
        "policies",
        "brightline",
        "supply",
        "does",
        "can",
        "must",
        "under",
        "into",
        "have",
        "has",
        "been",
        "about",
        "tell",
        "show",
        "explain",
    }
)


class DocumentQueryError(ValueError):
    """Raised when retrieval arguments are outside allowed bounds."""


def _cosine_distance(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 1.0
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a <= 1e-12 or norm_b <= 1e-12:
        return 1.0
    cosine_sim = max(-1.0, min(1.0, dot / (norm_a * norm_b)))
    return 1.0 - cosine_sim


def _lexical_overlap_boost(query: str, chunk_text: str, section_title: str, doc_key: str) -> float:
    """Compute a small deterministic lexical overlap boost [0.0, 0.18] for exact policy terms."""
    q_tokens = {
        t for t in _QUERY_TOKEN_RE.findall(query.lower()) if t not in _STOPWORDS and len(t) > 1
    }
    if not q_tokens:
        return 0.0
    haystack = f"{doc_key} {section_title} {chunk_text}".lower()
    h_tokens = set(_QUERY_TOKEN_RE.findall(haystack))
    matched = sum(1 for t in q_tokens if t in h_tokens or t.rstrip("s") in h_tokens)
    ratio = matched / len(q_tokens)
    return min(0.18, ratio * 0.18)


class DocumentRetrievalService:
    """Read-only, account-scoped policy document retrieval service."""

    def __init__(
        self,
        session: AsyncSession,
        account_id: uuid.UUID,
        embedder: EmbeddingClient,
        *,
        max_cosine_distance: float = 0.58,
    ) -> None:
        self._session = session
        self._account_id = account_id
        self._embedder = embedder
        self._max_cosine_distance = max_cosine_distance
        self._embedding_tokens_used = 0

    @property
    def embedding_tokens_used(self) -> int:
        return self._embedding_tokens_used

    async def search_documents(
        self,
        query: str,
        *,
        category: PolicyCategory | None = None,
        top_k: int = 4,
    ) -> DocumentSearchResult:
        cleaned_query = query.strip()
        if len(cleaned_query) < 2 or len(cleaned_query) > MAX_QUERY_LENGTH:
            raise DocumentQueryError(
                f"query length must be between 2 and {MAX_QUERY_LENGTH} characters."
            )
        if not (1 <= top_k <= MAX_TOP_K):
            raise DocumentQueryError(f"top_k must be between 1 and {MAX_TOP_K}.")
        if category is not None and category not in POLICY_CATEGORIES:
            raise DocumentQueryError(f"Invalid category '{category}'.")

        emb_batch = await self._embedder.embed_texts([cleaned_query])
        self._embedding_tokens_used += emb_batch.total_tokens
        query_vector = emb_batch.vectors[0]

        dialect = self._session.get_bind().dialect.name
        candidate_limit = min(24, max(top_k * 4, 12))

        filters = [
            DocumentChunk.account_id == self._account_id,
            PolicyDocument.account_id == self._account_id,
        ]
        if category is not None:
            filters.append(PolicyDocument.category == category)

        candidates: list[tuple[DocumentChunk, PolicyDocument, float]] = []

        if dialect == "postgresql":
            distance_expr = DocumentChunk.embedding.cosine_distance(query_vector).label(
                "cosine_distance"
            )
            stmt = (
                select(DocumentChunk, PolicyDocument, distance_expr)
                .join(
                    PolicyDocument,
                    and_(
                        PolicyDocument.id == DocumentChunk.document_id,
                        PolicyDocument.account_id == DocumentChunk.account_id,
                    ),
                )
                .where(*filters)
                .order_by(distance_expr.asc(), DocumentChunk.chunk_id.asc())
                .limit(candidate_limit)
            )
            rows = (await self._session.execute(stmt)).all()
            for chunk_row, doc_row, raw_dist in rows:
                candidates.append((chunk_row, doc_row, float(raw_dist)))
        else:
            stmt_fallback = (
                select(DocumentChunk, PolicyDocument)
                .join(
                    PolicyDocument,
                    and_(
                        PolicyDocument.id == DocumentChunk.document_id,
                        PolicyDocument.account_id == DocumentChunk.account_id,
                    ),
                )
                .where(*filters)
                .order_by(DocumentChunk.chunk_id.asc())
            )
            rows_fallback = (await self._session.execute(stmt_fallback)).all()
            for chunk_row, doc_row in rows_fallback:
                stored_vec = list(chunk_row.embedding) if chunk_row.embedding is not None else []
                dist = _cosine_distance(query_vector, stored_vec)
                candidates.append((chunk_row, doc_row, dist))

        scored: list[tuple[float, float, DocumentChunk, PolicyDocument]] = []
        for chunk_row, doc_row, raw_distance in candidates:
            boost = _lexical_overlap_boost(
                cleaned_query, chunk_row.content, chunk_row.section_title, doc_row.doc_key
            )
            effective_distance = max(0.0, raw_distance - boost)
            if effective_distance <= self._max_cosine_distance:
                similarity = round(max(0.0, min(1.0, 1.0 - effective_distance)), 4)
                scored.append((effective_distance, similarity, chunk_row, doc_row))

        scored.sort(key=lambda item: (item[0], item[2].chunk_id))
        top_matches = scored[:top_k]

        items = [
            RetrievedChunkItem(
                citation_id=chunk.chunk_id,
                doc_key=doc.doc_key,
                document_title=doc.title,
                category=cast(PolicyCategory, doc.category),
                version=doc.version,
                effective_date=doc.effective_date,
                section_title=chunk.section_title,
                page_number=chunk.page_number,
                similarity_score=sim,
                untrusted_document_excerpt=chunk.content,
            )
            for _dist, sim, chunk, doc in top_matches
        ]

        return DocumentSearchResult(
            query=cleaned_query,
            category_filter=category,
            has_evidence=len(items) > 0,
            returned=len(items),
            chunks=items,
        )
