"""Tests for strict AI tool dispatch, validation, bounds enforcement, and safety guards."""

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools import (
    MAX_RAW_ARGUMENT_BYTES,
    TOOLS,
    execute_tool,
)
from app.business.service import BusinessDataService
from tests.factories import AS_OF, build_business_fixture


@pytest.mark.asyncio
async def test_tool_registry_specifications() -> None:
    assert len(TOOLS) == 5
    for name, spec in TOOLS.items():
        assert spec.name == name
        assert len(spec.description) > 10
        assert spec.args_model is not None


@pytest.mark.asyncio
async def test_execute_tool_success_revenue(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    service = BusinessDataService(db_session, fix.account_a, AS_OF)

    args = json.dumps({"start_date": "2026-09-01", "end_date": "2026-09-30"})
    execution = await execute_tool(service, "get_revenue_summary", args)

    assert execution.ok is True
    assert execution.name == "get_revenue_summary"
    assert execution.result is not None
    assert execution.result["has_data"] is True
    assert execution.result["totals"][0]["invoiced"] == "1550.00"
    assert execution.payload["ok"] is True


@pytest.mark.asyncio
async def test_execute_tool_forbids_extra_arguments(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    service = BusinessDataService(db_session, fix.account_a, AS_OF)

    # Attempt to inject extra fields (e.g., account_id or SQL parameters)
    malicious_args = json.dumps(
        {
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
            "account_id": str(fix.account_b),
            "custom_sql": "SELECT * FROM users",
        }
    )
    execution = await execute_tool(service, "get_revenue_summary", malicious_args)

    assert execution.ok is False
    assert execution.error_code == "invalid_arguments"
    assert "extra" in (execution.error_message or "").lower()


@pytest.mark.asyncio
async def test_execute_tool_rejects_unknown_tool(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    service = BusinessDataService(db_session, fix.account_a, AS_OF)

    execution = await execute_tool(service, "execute_arbitrary_sql", "{}")
    assert execution.ok is False
    assert execution.error_code == "unknown_tool"


@pytest.mark.asyncio
async def test_execute_tool_rejects_malformed_json(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    service = BusinessDataService(db_session, fix.account_a, AS_OF)

    execution = await execute_tool(service, "get_revenue_summary", "{not-valid-json}")
    assert execution.ok is False
    assert execution.error_code == "invalid_arguments"


@pytest.mark.asyncio
async def test_execute_tool_rejects_payload_exceeding_byte_limit(
    db_session: AsyncSession,
) -> None:
    fix = await build_business_fixture(db_session)
    service = BusinessDataService(db_session, fix.account_a, AS_OF)

    oversized = json.dumps({"query": "A" * (MAX_RAW_ARGUMENT_BYTES + 10)})
    execution = await execute_tool(service, "search_customers", oversized)
    assert execution.ok is False
    assert execution.error_code == "invalid_arguments"
    assert "too large" in (execution.error_message or "").lower()


@pytest.mark.asyncio
async def test_execute_tool_bounds_checking(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    service = BusinessDataService(db_session, fix.account_a, AS_OF)

    # limit > MAX_UNPAID_LIMIT (50)
    args = json.dumps({"overdue_only": True, "limit": 999})
    execution = await execute_tool(service, "list_unpaid_invoices", args)
    assert execution.ok is False
    assert execution.error_code == "invalid_arguments"

    # end_date before start_date
    bad_dates = json.dumps({"start_date": "2026-10-15", "end_date": "2026-10-01"})
    execution_dates = await execute_tool(service, "get_revenue_summary", bad_dates)
    assert execution_dates.ok is False
    assert execution_dates.error_code == "invalid_arguments"


@pytest.mark.asyncio
async def test_execute_all_tools_smoke(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    service = BusinessDataService(db_session, fix.account_a, AS_OF)

    # list_unpaid_invoices
    res_unpaid = await execute_tool(
        service,
        "list_unpaid_invoices",
        json.dumps({"overdue_only": False, "limit": 10}),
    )
    assert res_unpaid.ok is True

    # get_customer_summary
    res_cust = await execute_tool(
        service,
        "get_customer_summary",
        json.dumps({"customer_ref": "CUST-0001"}),
    )
    assert res_cust.ok is True

    # search_customers
    res_search = await execute_tool(
        service,
        "search_customers",
        json.dumps({"query": "Acme"}),
    )
    assert res_search.ok is True

    # get_monthly_trend
    res_trend = await execute_tool(
        service,
        "get_monthly_trend",
        json.dumps({"months": 6, "end_month": "2026-10"}),
    )
    assert res_trend.ok is True
