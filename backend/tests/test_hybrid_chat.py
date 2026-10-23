"""Integration tests for Hybrid SQL + Document RAG chat orchestration, citations, and guards."""

import json
from collections.abc import Generator, Sequence

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import DeterministicEmbeddingClient
from app.ai.llm import ChatMessage, LLMResponse, ToolCallRequest
from app.ai.tools import ToolSpec
from app.api.v1.chat import get_as_of_date, get_embedding_client, get_llm_client
from app.config import get_settings
from app.documents.ingestion import ingest_policy_documents
from app.main import app
from tests.factories import AS_OF, build_business_fixture

settings = get_settings()


class ScriptedHybridLLM:
    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.recorded_messages: list[Sequence[ChatMessage]] = []

    @property
    def model(self) -> str:
        return "test-hybrid-mock"

    async def complete(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
    ) -> LLMResponse:
        self.recorded_messages.append(messages)
        if not self._responses:
            raise RuntimeError("Exhausted scripted responses")
        return self._responses.pop(0)


@pytest.fixture(autouse=True)
def override_chat_deps() -> Generator[None, None, None]:
    embedder = DeterministicEmbeddingClient()
    app.dependency_overrides[get_as_of_date] = lambda: AS_OF
    app.dependency_overrides[get_embedding_client] = lambda: embedder
    yield
    app.dependency_overrides.pop(get_as_of_date, None)
    app.dependency_overrides.pop(get_embedding_client, None)
    app.dependency_overrides.pop(get_llm_client, None)


def _auth_headers(token: str) -> tuple[dict[str, str], dict[str, str]]:
    csrf = "csrf-hybrid-test-token"
    cookies = {
        settings.SESSION_COOKIE_NAME: token,
        settings.CSRF_COOKIE_NAME: csrf,
    }
    headers = {"X-CSRF-Token": csrf}
    return cookies, headers


@pytest.mark.asyncio
async def test_hybrid_sql_and_rag_chat_returns_verified_citations(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    fix = await build_business_fixture(db_session)
    embedder = DeterministicEmbeddingClient()
    await ingest_policy_documents(db_session, account_id=fix.account_a, embedder=embedder)
    await db_session.commit()

    scripted = ScriptedHybridLLM(
        [
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallRequest(
                        id="tc_sql",
                        name="list_unpaid_invoices",
                        arguments=json.dumps({"overdue_only": True, "limit": 10}),
                    ),
                    ToolCallRequest(
                        id="tc_rag",
                        name="search_policy_documents",
                        arguments=json.dumps(
                            {
                                "query": "collections escalation tiers 90+ days overdue write-off",
                                "category": "collections",
                                "top_k": 3,
                            }
                        ),
                    ),
                ],
                input_tokens=360,
                output_tokens=60,
            ),
            LLMResponse(
                content=(
                    "Invoice INV-A5 (123.45 USD, 113 days overdue) falls into Tier 4 "
                    "(90+ days overdue) [DOC-COLLECTIONS#C01] and qualifies for "
                    "Small-Balance Write-Off Review (< 1,000.00 USD) "
                    "[DOC-COLLECTIONS#C04] [DOC-HALLUCINATED#C99]."
                ),
                input_tokens=820,
                output_tokens=55,
            ),
        ]
    )
    app.dependency_overrides[get_llm_client] = lambda: scripted

    cookies, headers = _auth_headers(fix.token_a)
    res = await async_client.post(
        "/api/v1/chat",
        json={"message": "Which overdue invoices violate our collections policy?"},
        cookies=cookies,
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert len(body["tool_calls"]) == 2
    assert [t["name"] for t in body["tool_calls"]] == [
        "list_unpaid_invoices",
        "search_policy_documents",
    ]
    # Fabricated citation tag is stripped from the answer and not returned in citations
    assert "DOC-HALLUCINATED#C99" not in body["answer"]
    citation_ids = [c["citation_id"] for c in body["citations"]]
    assert "DOC-COLLECTIONS#C01" in citation_ids
    assert "DOC-COLLECTIONS#C04" in citation_ids
    assert "DOC-HALLUCINATED#C99" not in citation_ids


@pytest.mark.asyncio
async def test_doc_only_chat_blocks_ungrounded_invoice_claims(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    fix = await build_business_fixture(db_session)
    embedder = DeterministicEmbeddingClient()
    await ingest_policy_documents(db_session, account_id=fix.account_a, embedder=embedder)
    await db_session.commit()

    scripted = ScriptedHybridLLM(
        [
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallRequest(
                        id="tc_rag_only",
                        name="search_policy_documents",
                        arguments=json.dumps(
                            {"query": "standard net payment terms", "category": "payment_terms"}
                        ),
                    )
                ],
                input_tokens=300,
                output_tokens=30,
            ),
            LLMResponse(
                # Model claims a customer balance not in policy docs without running SQL tools
                content=(
                    "Standard SMB terms are Net 30 [DOC-PAY-TERMS#C02] and "
                    "CUST-0001 owes 77,777.00 USD."
                ),
                input_tokens=500,
                output_tokens=28,
            ),
        ]
    )
    app.dependency_overrides[get_llm_client] = lambda: scripted

    cookies, headers = _auth_headers(fix.token_a)
    res = await async_client.post(
        "/api/v1/chat",
        json={"message": "What are our payment terms and how much does CUST-0001 owe?"},
        cookies=cookies,
        headers=headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ungrounded"
    assert "77,777.00" not in body["answer"]
    assert body["citations"] == []
