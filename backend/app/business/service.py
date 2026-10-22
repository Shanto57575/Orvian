"""Read-only, account-scoped business queries.

Security invariants:
- Every query is filtered by ``account_id`` bound at construction time from the authenticated
  user. Callers (including AI tools) can never supply or override the account.
- Only SQLAlchemy Core expressions with bound parameters are used; no raw SQL from input.
- All monetary arithmetic uses integer cents; conversion to ``Decimal`` happens at the edge.
"""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import Subquery, and_, extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.business.schemas import (
    AgingBucket,
    AgingBucketName,
    CustomerMatch,
    CustomerSearchResult,
    CustomerSummary,
    CustomerTotals,
    MonthlyPoint,
    MonthlyTrend,
    OutstandingTotal,
    RevenueSummary,
    RevenueTotals,
    UnpaidInvoiceRow,
    UnpaidInvoicesResult,
    cents_to_decimal,
)
from app.db.models import Customer, Invoice, Payment

MAX_RANGE_DAYS = 366 * 3
MAX_UNPAID_LIMIT = 50
MAX_SEARCH_LIMIT = 10
MAX_TREND_MONTHS = 24
_AGING_ORDER: tuple[AgingBucketName, ...] = ("current", "1-30", "31-60", "61-90", "90+")


class BusinessQueryError(ValueError):
    """Raised when a business query receives parameters outside the allowed bounds."""


def _aging_bucket(days_overdue: int) -> AgingBucketName:
    if days_overdue <= 0:
        return "current"
    if days_overdue <= 30:
        return "1-30"
    if days_overdue <= 60:
        return "31-60"
    if days_overdue <= 90:
        return "61-90"
    return "90+"


def _shift_month(month_start: date, delta: int) -> date:
    index = month_start.year * 12 + (month_start.month - 1) + delta
    return date(index // 12, index % 12 + 1, 1)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True)
class _OpenInvoice:
    currency: str
    due_date: date
    total_cents: int
    paid_cents: int

    @property
    def outstanding_cents(self) -> int:
        return self.total_cents - self.paid_cents


class BusinessDataService:
    """Approved read-only business queries for a single tenant account."""

    def __init__(self, session: AsyncSession, account_id: uuid.UUID, as_of: date) -> None:
        self._session = session
        self._account_id = account_id
        self._as_of = as_of

    @property
    def as_of(self) -> date:
        return self._as_of

    def _paid_subquery(self) -> Subquery:
        return (
            select(
                Payment.invoice_id.label("invoice_id"),
                func.sum(Payment.amount_cents).label("paid_cents"),
            )
            .where(Payment.account_id == self._account_id)
            .group_by(Payment.invoice_id)
            .subquery()
        )

    # ------------------------------------------------------------------
    # Revenue
    # ------------------------------------------------------------------
    async def revenue_summary(self, start: date, end: date) -> RevenueSummary:
        if end < start:
            raise BusinessQueryError("end_date must be on or after start_date.")
        if (end - start).days > MAX_RANGE_DAYS:
            raise BusinessQueryError("Date range may not exceed 3 years.")

        invoiced_rows = await self._session.execute(
            select(
                Invoice.currency,
                func.sum(Invoice.total_cents),
                func.count(Invoice.id),
            )
            .where(
                Invoice.account_id == self._account_id,
                Invoice.status != "void",
                Invoice.issue_date >= start,
                Invoice.issue_date <= end,
            )
            .group_by(Invoice.currency)
        )
        collected_rows = await self._session.execute(
            select(
                Invoice.currency,
                func.sum(Payment.amount_cents),
                func.count(Payment.id),
            )
            .join(
                Invoice,
                and_(
                    Invoice.id == Payment.invoice_id,
                    Invoice.account_id == Payment.account_id,
                ),
            )
            .where(
                Payment.account_id == self._account_id,
                Payment.paid_on >= start,
                Payment.paid_on <= end,
            )
            .group_by(Invoice.currency)
        )

        agg: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
        for currency, total, count in invoiced_rows.all():
            agg[currency][0] = int(total or 0)
            agg[currency][1] = int(count)
        for currency, total, count in collected_rows.all():
            agg[currency][2] = int(total or 0)
            agg[currency][3] = int(count)

        totals = [
            RevenueTotals(
                currency=currency,
                invoiced=cents_to_decimal(values[0]),
                invoice_count=values[1],
                collected=cents_to_decimal(values[2]),
                payment_count=values[3],
            )
            for currency, values in sorted(agg.items())
        ]
        return RevenueSummary(
            period_start=start, period_end=end, totals=totals, has_data=bool(totals)
        )

    # ------------------------------------------------------------------
    # Unpaid / overdue invoices
    # ------------------------------------------------------------------
    async def unpaid_invoices(
        self,
        *,
        overdue_only: bool = False,
        min_days_overdue: int = 0,
        customer_ref: str | None = None,
        limit: int = 20,
    ) -> UnpaidInvoicesResult:
        if not 1 <= limit <= MAX_UNPAID_LIMIT:
            raise BusinessQueryError(f"limit must be between 1 and {MAX_UNPAID_LIMIT}.")
        if not 0 <= min_days_overdue <= 3650:
            raise BusinessQueryError("min_days_overdue must be between 0 and 3650.")

        paid = self._paid_subquery()
        paid_cents = func.coalesce(paid.c.paid_cents, 0)
        stmt = (
            select(
                Invoice.invoice_number,
                Customer.external_ref,
                Customer.name,
                Invoice.issue_date,
                Invoice.due_date,
                Invoice.currency,
                Invoice.total_cents,
                paid_cents.label("paid_cents"),
            )
            .join(
                Customer,
                and_(
                    Customer.id == Invoice.customer_id,
                    Customer.account_id == Invoice.account_id,
                ),
            )
            .outerjoin(paid, paid.c.invoice_id == Invoice.id)
            .where(
                Invoice.account_id == self._account_id,
                Invoice.status == "open",
                Invoice.total_cents - paid_cents > 0,
            )
            .order_by(Invoice.due_date.asc(), Invoice.invoice_number.asc())
        )
        effective_overdue = overdue_only or min_days_overdue > 0
        if effective_overdue:
            cutoff = self._as_of - timedelta(days=max(1, min_days_overdue))
            stmt = stmt.where(Invoice.due_date <= cutoff)
        normalized_ref = customer_ref.strip().upper() if customer_ref else None
        if normalized_ref:
            stmt = stmt.where(Customer.external_ref == normalized_ref)

        rows = (await self._session.execute(stmt)).all()

        totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        aging: dict[tuple[AgingBucketName, str], list[int]] = defaultdict(lambda: [0, 0])
        invoices: list[UnpaidInvoiceRow] = []
        for number, ref, name, issue_date, due_date, currency, total, paid_value in rows:
            total_cents = int(total)
            paid_int = int(paid_value)
            outstanding = total_cents - paid_int
            days_overdue = max(0, (self._as_of - due_date).days)
            totals[currency][0] += 1
            totals[currency][1] += outstanding
            bucket = aging[(_aging_bucket(days_overdue), currency)]
            bucket[0] += 1
            bucket[1] += outstanding
            if len(invoices) < limit:
                invoices.append(
                    UnpaidInvoiceRow(
                        invoice_number=number,
                        customer_ref=ref,
                        customer_name=name,
                        issue_date=issue_date,
                        due_date=due_date,
                        days_overdue=days_overdue,
                        currency=currency,
                        total=cents_to_decimal(total_cents),
                        paid=cents_to_decimal(paid_int),
                        outstanding=cents_to_decimal(outstanding),
                    )
                )

        return UnpaidInvoicesResult(
            as_of=self._as_of,
            overdue_only=effective_overdue,
            min_days_overdue=min_days_overdue,
            customer_ref=normalized_ref,
            total_matching=len(rows),
            returned=len(invoices),
            truncated=len(rows) > len(invoices),
            totals=[
                OutstandingTotal(currency=c, invoice_count=v[0], outstanding=cents_to_decimal(v[1]))
                for c, v in sorted(totals.items())
            ],
            aging=[
                AgingBucket(
                    bucket=b, currency=c, invoice_count=v[0], outstanding=cents_to_decimal(v[1])
                )
                for (b, c), v in sorted(
                    aging.items(), key=lambda item: (item[0][1], _AGING_ORDER.index(item[0][0]))
                )
            ],
            invoices=invoices,
        )

    # ------------------------------------------------------------------
    # Customers
    # ------------------------------------------------------------------
    async def customer_summary(self, customer_ref: str) -> CustomerSummary:
        ref = customer_ref.strip().upper()
        customer = (
            await self._session.execute(
                select(Customer).where(
                    Customer.account_id == self._account_id,
                    Customer.external_ref == ref,
                )
            )
        ).scalar_one_or_none()
        if customer is None:
            return CustomerSummary(found=False, customer_ref=ref, as_of=self._as_of)

        paid = self._paid_subquery()
        invoice_rows = (
            await self._session.execute(
                select(
                    Invoice.currency,
                    Invoice.status,
                    Invoice.issue_date,
                    Invoice.due_date,
                    Invoice.total_cents,
                    func.coalesce(paid.c.paid_cents, 0),
                )
                .outerjoin(paid, paid.c.invoice_id == Invoice.id)
                .where(
                    Invoice.account_id == self._account_id,
                    Invoice.customer_id == customer.id,
                    Invoice.status != "void",
                )
            )
        ).all()
        payment_rows = (
            await self._session.execute(
                select(
                    Invoice.currency,
                    func.sum(Payment.amount_cents),
                    func.max(Payment.paid_on),
                )
                .join(
                    Invoice,
                    and_(
                        Invoice.id == Payment.invoice_id,
                        Invoice.account_id == Payment.account_id,
                    ),
                )
                .where(
                    Payment.account_id == self._account_id,
                    Invoice.customer_id == customer.id,
                )
                .group_by(Invoice.currency)
            )
        ).all()

        # currency -> [invoiced, collected, outstanding, overdue, open_count, overdue_count]
        agg: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0, 0])
        first_invoice: date | None = None
        for currency, status, issue_date, due_date, total, paid_value in invoice_rows:
            agg[currency][0] += int(total)
            first_invoice = issue_date if first_invoice is None else min(first_invoice, issue_date)
            if status == "open":
                inv = _OpenInvoice(currency, due_date, int(total), int(paid_value))
                if inv.outstanding_cents > 0:
                    agg[currency][2] += inv.outstanding_cents
                    agg[currency][4] += 1
                    if due_date < self._as_of:
                        agg[currency][3] += inv.outstanding_cents
                        agg[currency][5] += 1
        last_payment: date | None = None
        for currency, collected, last_paid in payment_rows:
            agg[currency][1] += int(collected or 0)
            if last_paid is not None:
                last_payment = last_paid if last_payment is None else max(last_payment, last_paid)

        return CustomerSummary(
            found=True,
            customer_ref=customer.external_ref,
            as_of=self._as_of,
            name=customer.name,
            industry=customer.industry,
            segment=customer.segment,
            country=customer.country,
            first_invoice_date=first_invoice,
            last_payment_date=last_payment,
            totals=[
                CustomerTotals(
                    currency=c,
                    invoiced=cents_to_decimal(v[0]),
                    collected=cents_to_decimal(v[1]),
                    outstanding=cents_to_decimal(v[2]),
                    overdue_outstanding=cents_to_decimal(v[3]),
                    open_invoice_count=v[4],
                    overdue_invoice_count=v[5],
                )
                for c, v in sorted(agg.items())
            ],
        )

    async def search_customers(self, query: str, limit: int = 5) -> CustomerSearchResult:
        cleaned = query.strip()
        if not cleaned:
            raise BusinessQueryError("query must not be empty.")
        if not 1 <= limit <= MAX_SEARCH_LIMIT:
            raise BusinessQueryError(f"limit must be between 1 and {MAX_SEARCH_LIMIT}.")
        pattern = f"%{_escape_like(cleaned)}%"
        rows = (
            await self._session.execute(
                select(Customer)
                .where(
                    Customer.account_id == self._account_id,
                    or_(
                        Customer.name.ilike(pattern, escape="\\"),
                        Customer.external_ref.ilike(pattern, escape="\\"),
                    ),
                )
                .order_by(Customer.name.asc())
                .limit(limit)
            )
        ).scalars()
        return CustomerSearchResult(
            query=cleaned,
            matches=[
                CustomerMatch(
                    customer_ref=c.external_ref,
                    name=c.name,
                    industry=c.industry,
                    segment=c.segment,
                    country=c.country,
                )
                for c in rows
            ],
        )

    # ------------------------------------------------------------------
    # Trends
    # ------------------------------------------------------------------
    async def monthly_trend(self, months: int = 12, end_month: date | None = None) -> MonthlyTrend:
        if not 1 <= months <= MAX_TREND_MONTHS:
            raise BusinessQueryError(f"months must be between 1 and {MAX_TREND_MONTHS}.")
        end_start = (end_month or self._as_of).replace(day=1)
        start = _shift_month(end_start, -(months - 1))
        end_exclusive = _shift_month(end_start, 1)

        inv_year = extract("year", Invoice.issue_date)
        inv_month = extract("month", Invoice.issue_date)
        invoiced = (
            await self._session.execute(
                select(inv_year, inv_month, Invoice.currency, func.sum(Invoice.total_cents))
                .where(
                    Invoice.account_id == self._account_id,
                    Invoice.status != "void",
                    Invoice.issue_date >= start,
                    Invoice.issue_date < end_exclusive,
                )
                .group_by(inv_year, inv_month, Invoice.currency)
            )
        ).all()
        pay_year = extract("year", Payment.paid_on)
        pay_month = extract("month", Payment.paid_on)
        collected = (
            await self._session.execute(
                select(pay_year, pay_month, Invoice.currency, func.sum(Payment.amount_cents))
                .join(
                    Invoice,
                    and_(
                        Invoice.id == Payment.invoice_id,
                        Invoice.account_id == Payment.account_id,
                    ),
                )
                .where(
                    Payment.account_id == self._account_id,
                    Payment.paid_on >= start,
                    Payment.paid_on < end_exclusive,
                )
                .group_by(pay_year, pay_month, Invoice.currency)
            )
        ).all()

        values: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
        currencies: set[str] = set()
        for year, month, currency, total in invoiced:
            values[(f"{int(year):04d}-{int(month):02d}", currency)][0] = int(total or 0)
            currencies.add(currency)
        for year, month, currency, total in collected:
            values[(f"{int(year):04d}-{int(month):02d}", currency)][1] = int(total or 0)
            currencies.add(currency)

        points: list[MonthlyPoint] = []
        for currency in sorted(currencies):
            for offset in range(months):
                label = _shift_month(start, offset).strftime("%Y-%m")
                inv_cents, col_cents = values.get((label, currency), [0, 0])
                points.append(
                    MonthlyPoint(
                        month=label,
                        currency=currency,
                        invoiced=cents_to_decimal(inv_cents),
                        collected=cents_to_decimal(col_cents),
                    )
                )
        return MonthlyTrend(
            start_month=start.strftime("%Y-%m"),
            end_month=end_start.strftime("%Y-%m"),
            has_data=bool(currencies),
            points=points,
        )
