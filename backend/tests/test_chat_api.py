"""Integration tests for the protected AI chat endpoint: auth, isolation, and bounded loop."""

import json
from collections.abc import Generator, Sequence

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm import ChatMessage, LLMError, LLMResponse, ToolCallRequest
from app.ai.orchestrator import LIMIT_REACHED_ANSWER, NO_ACCOUNT_ANSWER, UNGROUNDED_ANSWER
from app.ai.tools import ToolSpec
from app.api.v1.chat import get_as_of_date, get_llm_client
from app.config import get_settings
from app.main import app
from tests.factories import AS_OF, build_business_fixture, create_user_with_session

settings = get_settings()


class ScriptedLLMClient:
    """Deterministic fake LLM for testing orchestrator reactions without OpenAI API calls."""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self._responses = list(responses)
        self.recorded_messages: list[Sequence[ChatMessage]] = []
        self._model = "test-model-mock"

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
    ) -> LLMResponse:
        self.recorded_messages.append(messages)
        if not self._responses:
            raise RuntimeError("No more scripted responses.")
        resp = self._responses.pop(0)
        return resp


@pytest.fixture(autouse=True)
def override_as_of() -> Generator[None, None, None]:
    app.dependency_overrides[get_as_of_date] = lambda: AS_OF
    yield
    app.dependency_overrides.pop(get_as_of_date, None)


@pytest.mark.asyncio
async def test_chat_requires_authentication(async_client: AsyncClient) -> None:
    res = await async_client.post("/api/v1/chat", json={"message": "What is our revenue?"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_chat_requires_email_verification(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    fix = await build_business_fixture(db_session)
    _, unverified_token = await create_user_with_session(
        db_session, "unverified@example.com", fix.account_a, verified=False
    )

    # Use matching session + CSRF cookie & header
    async_client.cookies.set(settings.SESSION_COOKIE_NAME, unverified_token)
    async_client.cookies.set(settings.CSRF_COOKIE_NAME, "test-csrf-token")
    res = await async_client.post(
        "/api/v1/chat",
        json={"message": "What is our revenue?"},
        headers={"X-CSRF-Token": "test-csrf-token"},
    )
    assert res.status_code == 403
    assert "email verification required" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_chat_validates_csrf_for_cookie_sessions(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    fix = await build_business_fixture(db_session)

    # Session cookie without CSRF cookie/header -> 403
    async_client.cookies.set(settings.SESSION_COOKIE_NAME, fix.token_a)
    res_no_csrf = await async_client.post("/api/v1/chat", json={"message": "What is our revenue?"})
    assert res_no_csrf.status_code == 403
    assert "CSRF validation failed" in res_no_csrf.json()["detail"]


@pytest.mark.asyncio
async def test_chat_user_without_account_returns_safe_no_data(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    # User has no linked account_id
    _, token = await create_user_with_session(
        db_session, "no-account@example.com", account_id=None, verified=True
    )
    res = await async_client.post(
        "/api/v1/chat",
        json={"message": "What is our revenue?"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "no_data"
    assert data["answer"] == NO_ACCOUNT_ANSWER
    assert data["tool_calls"] == []


@pytest.mark.asyncio
async def test_chat_missing_llm_key_returns_503(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    fix = await build_business_fixture(db_session)

    # Override get_llm_client to return None (simulating missing OPENAI_API_KEY)
    app.dependency_overrides[get_llm_client] = lambda: None
    try:
        res = await async_client.post(
            "/api/v1/chat",
            json={"message": "What is our revenue?"},
            headers={"Authorization": f"Bearer {fix.token_a}"},
        )
        assert res.status_code == 503
        detail = res.json()["detail"]
        assert detail["code"] == "llm_not_configured"
    finally:
        app.dependency_overrides.pop(get_llm_client, None)


@pytest.mark.asyncio
async def test_chat_successful_tool_flow_tenant_isolated(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    fix = await build_business_fixture(db_session)

    # Scripted LLM:
    # Round 1: Model requests get_revenue_summary
    # Round 2: Model uses returned tool data to answer
    scripted = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCallRequest(
                        id="call_1",
                        name="get_revenue_summary",
                        arguments=json.dumps(
                            {"start_date": "2026-09-01", "end_date": "2026-09-30"}
                        ),
                    )
                ],
                input_tokens=50,
                output_tokens=20,
            ),
            LLMResponse(
                content=(
                    "In September 2026, total invoiced revenue was USD 1,550.00 "
                    "and collected cash was USD 1,000.00."
                ),
                tool_calls=[],
                input_tokens=120,
                output_tokens=35,
            ),
        ]
    )
    app.dependency_overrides[get_llm_client] = lambda: scripted
    try:
        res = await async_client.post(
            "/api/v1/chat",
            json={"message": "How much did we invoice and collect in Sept 2026?"},
            headers={
                "Authorization": f"Bearer {fix.token_a}",
                "X-Request-ID": "test-req-12345678",
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert "1,550.00" in data["answer"]
        assert data["correlation_id"] == "test-req-12345678"
        assert len(data["tool_calls"]) == 1
        t_call = data["tool_calls"][0]
        assert t_call["name"] == "get_revenue_summary"
        assert t_call["ok"] is True
        assert t_call["result"]["totals"][0]["invoiced"] == "1550.00"
        assert data["usage"]["input_tokens"] == 170
        assert data["usage"]["output_tokens"] == 55

        # Check that the tool result passed back to the LLM contained Tenant A's data
        tool_msg = scripted.recorded_messages[1][-1]
        assert tool_msg["role"] == "tool"
        assert "1550.00" in tool_msg["content"]
        assert "14999.99" not in tool_msg["content"]  # Tenant B data NOT leaked
    finally:
        app.dependency_overrides.pop(get_llm_client, None)


@pytest.mark.asyncio
async def test_chat_withholds_ungrounded_hallucinations(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    fix = await build_business_fixture(db_session)

    # Model hallucinates monetary figures without ever calling a tool
    hallucinating_llm = ScriptedLLMClient(
        [
            LLMResponse(
                content="You made $1,000,000.00 last month!",
                tool_calls=[],
            )
        ]
    )
    app.dependency_overrides[get_llm_client] = lambda: hallucinating_llm
    try:
        res = await async_client.post(
            "/api/v1/chat",
            json={"message": "How much did we make?"},
            headers={"Authorization": f"Bearer {fix.token_a}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ungrounded"
        assert data["answer"] == UNGROUNDED_ANSWER
        assert data["tool_calls"] == []
    finally:
        app.dependency_overrides.pop(get_llm_client, None)


@pytest.mark.asyncio
async def test_chat_bounds_tool_iterations(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    fix = await build_business_fixture(db_session)

    # Looping model requesting tools forever
    loop_response = LLMResponse(
        content=None,
        tool_calls=[
            ToolCallRequest(
                id="call_loop",
                name="search_customers",
                arguments=json.dumps({"query": "Acme"}),
            )
        ],
    )
    looping_llm = ScriptedLLMClient([loop_response] * 10)
    app.dependency_overrides[get_llm_client] = lambda: looping_llm
    try:
        res = await async_client.post(
            "/api/v1/chat",
            json={"message": "Loop query"},
            headers={"Authorization": f"Bearer {fix.token_a}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "limit_reached"
        assert data["answer"] == LIMIT_REACHED_ANSWER
        assert len(data["tool_calls"]) <= settings.LLM_MAX_TOOL_CALLS
    finally:
        app.dependency_overrides.pop(get_llm_client, None)


class FailingLLMClient:
    @property
    def model(self) -> str:
        return "failing-model"

    async def complete(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
    ) -> LLMResponse:
        raise LLMError("rate_limited")


@pytest.mark.asyncio
async def test_chat_handles_llm_provider_errors(
    async_client: AsyncClient, db_session: AsyncSession
) -> None:
    fix = await build_business_fixture(db_session)

    app.dependency_overrides[get_llm_client] = lambda: FailingLLMClient()
    try:
        res = await async_client.post(
            "/api/v1/chat",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {fix.token_a}"},
        )
        assert res.status_code == 502
        assert res.json()["detail"]["code"] == "llm_unavailable"
    finally:
        app.dependency_overrides.pop(get_llm_client, None)
