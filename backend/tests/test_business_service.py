"""Tests for business data services: financial calculations, boundaries, and isolation."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.schemas import cents_to_decimal
from app.business.service import BusinessDataService, BusinessQueryError
from tests.factories import AS_OF, build_business_fixture


def test_cents_to_decimal() -> None:
    assert cents_to_decimal(100) == Decimal("1.00")
    assert cents_to_decimal(12345) == Decimal("123.45")
    assert cents_to_decimal(0) == Decimal("0.00")
    assert cents_to_decimal(5) == Decimal("0.05")


@pytest.mark.asyncio
async def test_revenue_summary_invoiced_and_collected(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    service = BusinessDataService(db_session, fix.account_a, AS_OF)

    # September 2026:
    # Invoices non-void in Sept for A:
    # INV-A1 (1000.00), INV-A2 (540.00), INV-A6 (10.00). Total invoiced = 1550.00 (3 invoices)
    # Payments in Sept for A:
    # INV-A1 payment 1000.00 on 2026-09-20. Total collected = 1000.00 (1 payment)
    rev_sept = await service.revenue_summary(date(2026, 9, 1), date(2026, 9, 30))
    assert rev_sept.has_data is True
    assert len(rev_sept.totals) == 1
    t_sept = rev_sept.totals[0]
    assert t_sept.currency == "USD"
    assert t_sept.invoiced == Decimal("1550.00")
    assert t_sept.invoice_count == 3
    assert t_sept.collected == Decimal("1000.00")
    assert t_sept.payment_count == 1

    # October 2026 (up to AS_OF 10-22):
    # Invoices non-void in Oct: INV-A3 (250.50). Total invoiced = 250.50 (1 invoice)
    # Payments in Oct: INV-A2 partial 200.00 on 2026-10-01. Total collected = 200.00 (1 payment)
    rev_oct = await service.revenue_summary(date(2026, 10, 1), date(2026, 10, 22))
    assert rev_oct.has_data is True
    t_oct = rev_oct.totals[0]
    assert t_oct.invoiced == Decimal("250.50")
    assert t_oct.invoice_count == 1
    assert t_oct.collected == Decimal("200.00")
    assert t_oct.payment_count == 1


@pytest.mark.asyncio
async def test_revenue_summary_date_validation(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    service = BusinessDataService(db_session, fix.account_a, AS_OF)

    with pytest.raises(BusinessQueryError, match="end_date must be on or after start_date"):
        await service.revenue_summary(date(2026, 10, 2), date(2026, 10, 1))

    with pytest.raises(BusinessQueryError, match="Date range may not exceed 3 years"):
        await service.revenue_summary(date(2020, 1, 1), date(2025, 1, 1))


@pytest.mark.asyncio
async def test_tenant_isolation_revenue(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    service_a = BusinessDataService(db_session, fix.account_a, AS_OF)
    service_b = BusinessDataService(db_session, fix.account_b, AS_OF)
    service_empty = BusinessDataService(db_session, fix.empty_account, AS_OF)

    rev_a = await service_a.revenue_summary(date(2026, 9, 1), date(2026, 9, 30))
    rev_b = await service_b.revenue_summary(date(2026, 9, 1), date(2026, 9, 30))
    rev_empty = await service_empty.revenue_summary(date(2026, 9, 1), date(2026, 9, 30))

    # Tenant B has INV-B1 (9999.99 open) and INV-B2 (5000.00 paid on 09-05)
    assert rev_b.totals[0].invoiced == Decimal("14999.99")
    assert rev_b.totals[0].collected == Decimal("5000.00")

    # Tenant A results do not leak into Tenant B
    assert rev_a.totals[0].invoiced != rev_b.totals[0].invoiced

    # Empty account has no data
    assert rev_empty.has_data is False
    assert len(rev_empty.totals) == 0


@pytest.mark.asyncio
async def test_unpaid_and_overdue_invoices(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    service = BusinessDataService(db_session, fix.account_a, AS_OF)

    # All unpaid for Tenant A:
    # 1. INV-A5: due 2026-07-01, outstanding 123.45 (113 days overdue)
    # 2. INV-A2: due 2026-10-15, total 540.00, paid 200.00, outstanding 340.00 (7 days overdue)
    # 3. INV-A6: due 2026-10-22 (today!), outstanding 10.00 (0 days overdue, not overdue yet)
    # 4. INV-A3: due 2026-11-04, outstanding 250.50 (due in future, not overdue)
    # Note: INV-A4 is void (excluded), INV-A1 is paid (excluded).
    unpaid = await service.unpaid_invoices(overdue_only=False)
    assert unpaid.total_matching == 4
    assert len(unpaid.invoices) == 4
    assert unpaid.totals[0].outstanding == Decimal("723.95")  # 123.45 + 340.00 + 10.00 + 250.50

    # Test overdue only (due strictly before AS_OF 2026-10-22):
    # INV-A5 (due 07-01) and INV-A2 (due 10-15).
    # INV-A6 due today (10-22) is NOT overdue.
    overdue = await service.unpaid_invoices(overdue_only=True)
    assert overdue.total_matching == 2
    assert len(overdue.invoices) == 2
    assert overdue.invoices[0].invoice_number == "INV-A5"
    assert overdue.invoices[0].days_overdue == 113
    assert overdue.invoices[1].invoice_number == "INV-A2"
    assert overdue.invoices[1].days_overdue == 7
    assert overdue.totals[0].outstanding == Decimal("463.45")  # 123.45 + 340.00

    # Aging buckets check on unpaid
    # current: INV-A6 (10.00) + INV-A3 (250.50) = 260.50 (2 invoices)
    # 1-30: INV-A2 (340.00, 7 days overdue) = 340.00 (1 invoice)
    # 90+: INV-A5 (123.45, 113 days overdue) = 123.45 (1 invoice)
    bucket_map = {b.bucket: b.outstanding for b in unpaid.aging}
    assert bucket_map.get("current") == Decimal("260.50")
    assert bucket_map.get("1-30") == Decimal("340.00")
    assert bucket_map.get("90+") == Decimal("123.45")


@pytest.mark.asyncio
async def test_unpaid_invoices_filters_and_limits(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    service = BusinessDataService(db_session, fix.account_a, AS_OF)

    # Filter by customer CUST-0001: should only return INV-A2 and INV-A6
    cust_res = await service.unpaid_invoices(customer_ref="CUST-0001")
    assert cust_res.total_matching == 2
    assert {inv.invoice_number for inv in cust_res.invoices} == {"INV-A2", "INV-A6"}

    # Limit testing & truncation flag
    lim_res = await service.unpaid_invoices(limit=1)
    assert lim_res.total_matching == 4
    assert lim_res.returned == 1
    assert lim_res.truncated is True

    # Bad limit
    with pytest.raises(BusinessQueryError, match="limit must be between 1 and"):
        await service.unpaid_invoices(limit=0)


@pytest.mark.asyncio
async def test_customer_summary(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    service = BusinessDataService(db_session, fix.account_a, AS_OF)

    # CUST-0001 for Account A:
    # INV-A1: 1000.00 (paid, payment 1000.00)
    # INV-A2: 540.00 (open, payment 200.00 -> outstanding 340.00 overdue)
    # INV-A6: 10.00 (open, payment 0.00 -> outstanding 10.00 not overdue)
    # Totals:
    # Invoiced = 1550.00
    # Collected = 1200.00
    # Outstanding = 350.00
    # Overdue outstanding = 340.00
    # Open invoice count = 2
    # Overdue invoice count = 1
    summary = await service.customer_summary("CUST-0001")
    assert summary.found is True
    assert summary.name == "Acme Test Co"
    assert len(summary.totals) == 1
    t = summary.totals[0]
    assert t.invoiced == Decimal("1550.00")
    assert t.collected == Decimal("1200.00")
    assert t.outstanding == Decimal("350.00")
    assert t.overdue_outstanding == Decimal("340.00")
    assert t.open_invoice_count == 2
    assert t.overdue_invoice_count == 1

    # Non-existent customer
    non_existent = await service.customer_summary("NON-EXISTENT")
    assert non_existent.found is False
    assert len(non_existent.totals) == 0


@pytest.mark.asyncio
async def test_search_customers(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    service = BusinessDataService(db_session, fix.account_a, AS_OF)

    # Partial name match
    res1 = await service.search_customers("Acme")
    assert len(res1.matches) == 1
    assert res1.matches[0].customer_ref == "CUST-0001"

    # Search by ref
    res2 = await service.search_customers("CUST-0002")
    assert len(res2.matches) == 1
    assert res2.matches[0].customer_ref == "CUST-0002"

    # Does not find Tenant B customer
    res3 = await service.search_customers("Other Tenant")
    assert len(res3.matches) == 0


@pytest.mark.asyncio
async def test_monthly_trend(db_session: AsyncSession) -> None:
    fix = await build_business_fixture(db_session)
    service = BusinessDataService(db_session, fix.account_a, AS_OF)

    # Trend for last 3 months: 2026-08, 2026-09, 2026-10
    trend = await service.monthly_trend(months=3, end_month=date(2026, 10, 1))
    assert trend.has_data is True
    points = {p.month: p for p in trend.points}
    assert "2026-08" in points
    assert "2026-09" in points
    assert "2026-10" in points

    # August has 0 invoiced, 0 collected
    assert points["2026-08"].invoiced == Decimal("0.00")
    assert points["2026-08"].collected == Decimal("0.00")

    # September
    assert points["2026-09"].invoiced == Decimal("1550.00")
    assert points["2026-09"].collected == Decimal("1000.00")

    # October
    assert points["2026-10"].invoiced == Decimal("250.50")
    assert points["2026-10"].collected == Decimal("200.00")
