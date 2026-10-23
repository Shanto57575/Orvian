"""Embedding client abstraction and OpenAI implementation.

 Retrieval and ingestion depend only on ``EmbeddingClient``.
``OpenAIEmbeddingClient`` uses the official OpenAI SDK (`AsyncOpenAI.embeddings.create`)
with explicit ``encoding_format="float"`` and configurable dimensions.
``DeterministicEmbeddingClient`` provides an offline, zero-cost semantic-keyword + hashed
unit-vector embedder for tests and offline evaluation.
"""

import hashlib
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import openai
from openai import AsyncOpenAI


class EmbeddingError(Exception):
    """Embedding provider call failed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class EmbeddingBatchResult:
    vectors: list[list[float]]
    total_tokens: int


class EmbeddingClient(Protocol):
    @property
    def model(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    async def embed_texts(self, texts: Sequence[str]) -> EmbeddingBatchResult: ...


class OpenAIEmbeddingClient:
    """Official OpenAI embeddings client producing float vectors of fixed dimension."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int = 1536,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
    ) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            timeout=timeout_seconds,
            max_retries=max_retries,
        )
        self._model = model
        self._dimensions = dimensions

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_texts(self, texts: Sequence[str]) -> EmbeddingBatchResult:
        if not texts:
            return EmbeddingBatchResult(vectors=[], total_tokens=0)

        cleaned = [t.strip() or " " for t in texts]
        try:
            response = await self._client.embeddings.create(
                model=self._model,
                input=cleaned,
                dimensions=self._dimensions,
                encoding_format="float",
            )
        except openai.APITimeoutError as exc:
            raise EmbeddingError("timeout") from exc
        except openai.RateLimitError as exc:
            raise EmbeddingError("rate_limited") from exc
        except openai.AuthenticationError as exc:
            raise EmbeddingError("auth_failed") from exc
        except openai.OpenAIError as exc:
            raise EmbeddingError("provider_error") from exc

        ordered: list[list[float] | None] = [None] * len(cleaned)
        for item in response.data:
            if 0 <= item.index < len(ordered):
                ordered[item.index] = list(item.embedding)

        vectors: list[list[float]] = []
        for vec in ordered:
            if vec is None or len(vec) != self._dimensions:
                raise EmbeddingError("invalid_embedding_response")
            vectors.append(vec)

        usage = response.usage
        total_tokens = usage.total_tokens if usage else 0
        return EmbeddingBatchResult(vectors=vectors, total_tokens=total_tokens)


# Domain concept clusters for deterministic offline embeddings so semantic synonyms align in tests.
_CONCEPT_CLUSTERS: tuple[tuple[str, ...], ...] = (
    ("payment", "terms", "net", "30", "45", "smb", "mid_market", "enterprise", "due", "billing"),
    ("grace", "period", "late", "fee", "interest", "apr", "1.5%", "penalty", "waiver"),
    ("method", "check", "ach", "bank_transfer", "wire", "card", "crypto", "cryptocurrency", "cash"),
    (
        "collection",
        "collections",
        "escalation",
        "overdue",
        "aging",
        "dunning",
        "delinquent",
        "tier",
    ),
    ("hold", "shipment", "soft", "hard", "suspend", "suspension", "demand", "notice"),
    ("agency", "legal", "external", "write-off", "writeoff", "90", "90+", "severe", "workout"),
    ("dispute", "disputes", "billing", "15", "window", "inaccurate", "discrepancy"),
    ("rma", "defective", "damaged", "return", "restocking", "merchandise"),
    ("refund", "refunds", "credit", "memo", "overpayment", "reimbursement", "cash"),
    (
        "approval",
        "matrix",
        "manager",
        "controller",
        "vp",
        "finance",
        "cfo",
        "sign-off",
        "authorize",
    ),
    ("limit", "limits", "exposure", "cap", "utilization", "breach", "violation", "risk"),
    ("reinstatement", "uplift", "temporary", "increase", "80%", "50%", "100%"),
    ("tax", "sales", "8%", "8.0%", "cents", "subtotal", "ledger", "precision"),
    ("sla", "posting", "application", "remittance", "lockbox", "24", "hours", "partial"),
    ("void", "voiding", "cancel", "cancelled", "close", "cutoff", "month-end", "subledger"),
)

_TOKEN_RE = re.compile(r"[a-z0-9_+%.-]+")
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
    }
)


def _stem(word: str) -> str:
    w = word.lower().strip(".,:;!?()[]{}\"'")
    if len(w) > 5 and w.endswith("ing"):
        return w[:-3]
    if len(w) > 4 and w.endswith("es"):
        return w[:-2]
    if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
        return w[:-1]
    return w


class DeterministicEmbeddingClient:
    """Offline unit-normalized feature-hash + domain-concept embedder for deterministic tests."""

    def __init__(
        self, dimensions: int = 1536, model_name: str = "deterministic-test-embedder"
    ) -> None:
        self._dimensions = dimensions
        self._model = model_name

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dimensions
        raw_tokens = _TOKEN_RE.findall(text.lower())
        tokens = [_stem(t) for t in raw_tokens if t not in _STOPWORDS and len(t) > 1]

        if not tokens:
            vec[0] = 1.0
            return vec

        # 1. Concept cluster dimensions (first len(_CONCEPT_CLUSTERS) * 4 slots)
        token_set = set(tokens) | set(raw_tokens)
        for cluster_idx, cluster in enumerate(_CONCEPT_CLUSTERS):
            stemmed_cluster = {_stem(c) for c in cluster} | set(cluster)
            overlap = len(token_set & stemmed_cluster)
            if overlap > 0:
                base_slot = (cluster_idx * 4) % self._dimensions
                weight = 1.8 * math.log1p(overlap)
                for offset in range(4):
                    vec[(base_slot + offset) % self._dimensions] += weight

        # 2. Unigram and bigram feature hashing into remaining slots
        features = list(tokens)
        for i in range(len(tokens) - 1):
            features.append(f"{tokens[i]}_{tokens[i + 1]}")

        for feat in features:
            digest = hashlib.sha256(feat.encode("utf-8")).digest()
            idx = 64 + (int.from_bytes(digest[:4], "big") % max(1, self._dimensions - 64))
            sign = 1.0 if (digest[4] & 1) == 0 else -1.0
            vec[idx] += sign * 1.0

        norm = math.sqrt(sum(v * v for v in vec))
        if norm <= 1e-12:
            vec[0] = 1.0
            return vec
        return [round(v / norm, 7) for v in vec]

    async def embed_texts(self, texts: Sequence[str]) -> EmbeddingBatchResult:
        vectors = [self.embed_one(t) for t in texts]
        approx_tokens = sum(max(1, len(t.split())) for t in texts)
        return EmbeddingBatchResult(vectors=vectors, total_tokens=approx_tokens)
