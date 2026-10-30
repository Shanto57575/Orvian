"""Deterministic and Live-LLM evaluation runner with latency, token, and cost telemetry."""

import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import EmbeddingClient
from app.ai.llm import ChatMessage, LLMClient, LLMResponse
from app.ai.orchestrator import run_chat
from app.ai.tools import ToolSpec
from app.business.service import BusinessDataService
from app.documents.service import DocumentRetrievalService
from app.evals.cases import EVAL_CASES, EvalCase

# Pricing constants for gpt-4o-mini ($0.15 / 1M input, $0.60 / 1M output)
# and text-embedding-3-small ($0.02 / 1M tokens)
GPT4O_MINI_INPUT_COST_PER_TOKEN = 0.15 / 1_000_000
GPT4O_MINI_OUTPUT_COST_PER_TOKEN = 0.60 / 1_000_000
EMBEDDING_SMALL_COST_PER_TOKEN = 0.02 / 1_000_000


class ScriptedEvalLLMClient:
    """Replays pre-scripted LLM responses for deterministic, zero-cost evaluation."""

    def __init__(self, responses: Sequence[LLMResponse]) -> None:
        self._responses = list(responses)
        self._model = "scripted-eval-mock"

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self, messages: Sequence[ChatMessage], tools: Sequence[ToolSpec]
    ) -> LLMResponse:
        if not self._responses:
            raise RuntimeError("ScriptedEvalLLMClient exhausted all responses.")
        return self._responses.pop(0)


@dataclass
class EvalCaseResult:
    case_id: str
    category: str
    description: str
    passed: bool
    status: str
    expected_status: str
    tools_called: list[str]
    citations_returned: list[str]
    latency_ms: float
    input_tokens: int
    output_tokens: int
    embedding_tokens: int
    estimated_cost_usd: float
    failures: list[str] = field(default_factory=list)
    answer_preview: str = ""


@dataclass
class EvalSuiteReport:
    mode: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    pass_rate_percent: float
    total_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int
    total_embedding_tokens: int
    total_estimated_cost_usd: float
    results: list[EvalCaseResult]


def grade_eval_case(
    case: EvalCase,
    *,
    actual_status: str,
    answer: str,
    tools_called: list[str],
    citation_ids: list[str],
    citation_doc_keys: list[str],
) -> list[str]:
    """Perform deterministic checks on an evaluation outcome. Returns a list of failure reasons."""
    failures: list[str] = []

    if actual_status != case.expected_status:
        failures.append(
            f"status mismatch: expected '{case.expected_status}', got '{actual_status}'"
        )

    called_set = set(tools_called)
    for req_tool in case.required_tools:
        if req_tool not in called_set:
            failures.append(f"missing required tool '{req_tool}' (called: {tools_called})")

    for forb_tool in case.forbidden_tools:
        if forb_tool in called_set:
            failures.append(f"called forbidden tool '{forb_tool}'")

    lower_ans = answer.lower()
    for term in case.must_contain_all:
        if term.lower() not in lower_ans:
            failures.append(f"answer missing required substring '{term}'")

    if case.must_contain_any and not any(t.lower() in lower_ans for t in case.must_contain_any):
        failures.append(f"answer did not contain any of {case.must_contain_any}")

    for forbidden in case.must_not_contain:
        if forbidden.lower() in lower_ans:
            failures.append(f"answer contained forbidden substring '{forbidden}'")

    if len(citation_ids) < case.min_citations:
        failures.append(
            f"expected at least {case.min_citations} verified citations, got {len(citation_ids)}"
        )

    doc_key_set = set(citation_doc_keys)
    for req_doc_key in case.required_citation_doc_keys:
        if req_doc_key not in doc_key_set:
            failures.append(
                f"missing required citation doc_key '{req_doc_key}' (got: {citation_doc_keys})"
            )

    return failures


async def run_single_eval_case(
    case: EvalCase,
    *,
    session: AsyncSession,
    account_id: uuid.UUID,
    as_of: date,
    embedder: EmbeddingClient,
    live_llm: LLMClient | None = None,
    max_cosine_distance: float = 0.58,
) -> EvalCaseResult:
    llm: LLMClient = (
        live_llm if live_llm is not None else ScriptedEvalLLMClient(case.scripted_responses)
    )
    business_service = BusinessDataService(session, account_id, as_of)
    doc_service = DocumentRetrievalService(
        session,
        account_id,
        embedder,
        max_cosine_distance=max_cosine_distance,
    )

    started = time.perf_counter()
    outcome = await run_chat(
        llm=llm,
        service=business_service,
        document_service=doc_service,
        message=case.question,
        as_of=as_of,
        max_iterations=5,
        max_tool_calls=8,
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 2)

    tools_called = [t.name for t in outcome.tool_calls]
    citation_ids = [c.citation_id for c in outcome.citations]
    citation_doc_keys = [c.doc_key for c in outcome.citations]

    failures = grade_eval_case(
        case,
        actual_status=outcome.status,
        answer=outcome.answer,
        tools_called=tools_called,
        citation_ids=citation_ids,
        citation_doc_keys=citation_doc_keys,
    )

    emb_tokens = doc_service.embedding_tokens_used
    est_cost = (
        outcome.input_tokens * GPT4O_MINI_INPUT_COST_PER_TOKEN
        + outcome.output_tokens * GPT4O_MINI_OUTPUT_COST_PER_TOKEN
        + emb_tokens * EMBEDDING_SMALL_COST_PER_TOKEN
    )

    return EvalCaseResult(
        case_id=case.case_id,
        category=case.category,
        description=case.description,
        passed=len(failures) == 0,
        status=outcome.status,
        expected_status=case.expected_status,
        tools_called=tools_called,
        citations_returned=citation_ids,
        latency_ms=latency_ms,
        input_tokens=outcome.input_tokens,
        output_tokens=outcome.output_tokens,
        embedding_tokens=emb_tokens,
        estimated_cost_usd=round(est_cost, 6),
        failures=failures,
        answer_preview=outcome.answer[:240],
    )


async def run_evaluation_suite(
    *,
    session: AsyncSession,
    account_id: uuid.UUID,
    as_of: date,
    embedder: EmbeddingClient,
    live_llm: LLMClient | None = None,
    cases: Sequence[EvalCase] = EVAL_CASES,
    max_cosine_distance: float = 0.58,
) -> EvalSuiteReport:
    results: list[EvalCaseResult] = []
    for case in cases:
        res = await run_single_eval_case(
            case,
            session=session,
            account_id=account_id,
            as_of=as_of,
            embedder=embedder,
            live_llm=live_llm,
            max_cosine_distance=max_cosine_distance,
        )
        results.append(res)

    passed = sum(1 for r in results if r.passed)
    total = len(results)
    pass_rate = round((passed / total) * 100.0, 2) if total else 0.0

    return EvalSuiteReport(
        mode="live" if live_llm is not None else "deterministic",
        total_cases=total,
        passed_cases=passed,
        failed_cases=total - passed,
        pass_rate_percent=pass_rate,
        total_latency_ms=round(sum(r.latency_ms for r in results), 2),
        total_input_tokens=sum(r.input_tokens for r in results),
        total_output_tokens=sum(r.output_tokens for r in results),
        total_embedding_tokens=sum(r.embedding_tokens for r in results),
        total_estimated_cost_usd=round(sum(r.estimated_cost_usd for r in results), 6),
        results=results,
    )
