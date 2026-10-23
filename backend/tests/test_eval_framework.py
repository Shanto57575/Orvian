"""Automated test suite executing all 24 Hybrid SQL + Document RAG evaluation cases."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import DeterministicEmbeddingClient
from app.evals.cases import EVAL_CASES
from app.evals.runner import run_evaluation_suite
from scripts.run_evals import EVAL_AS_OF, seed_eval_fixture


def test_eval_suite_has_at_least_20_cases_across_all_categories() -> None:
    assert len(EVAL_CASES) >= 20
    categories = {c.category for c in EVAL_CASES}
    assert categories == {
        "sql_only",
        "doc_only",
        "hybrid_sql_rag",
        "missing_evidence",
        "contradictory_evidence",
        "cross_account_isolation",
        "prompt_injection",
        "tool_and_grounding_guards",
    }


@pytest.mark.asyncio
async def test_run_full_deterministic_evaluation_suite(db_session: AsyncSession) -> None:
    embedder = DeterministicEmbeddingClient()
    account_a_id, _ = await seed_eval_fixture(db_session, embedder)

    report = await run_evaluation_suite(
        session=db_session,
        account_id=account_a_id,
        as_of=EVAL_AS_OF,
        embedder=embedder,
        live_llm=None,
    )

    failed_details = [f"{r.case_id}: {r.failures}" for r in report.results if not r.passed]
    assert report.failed_cases == 0, f"Evaluation failures: {failed_details}"
    assert report.passed_cases == len(EVAL_CASES)
    assert report.pass_rate_percent == 100.0
