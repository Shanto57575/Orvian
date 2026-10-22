"""Typed result models for business data services.

Monetary values are exact ``Decimal`` amounts derived from integer cents and always carry
an explicit ISO 4217 currency code. Pydantic serializes ``Decimal`` as a JSON string, so no
binary floating point is introduced anywhere between the database and the API response.
"""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


def cents_to_decimal(cents: int) -> Decimal:
    """Convert integer minor units to an exact two-decimal amount."""
    return (Decimal(cents) / Decimal(100)).quantize(Decimal("0.01"))


class _Result(BaseModel):
    model_config = ConfigDict(frozen=True)


class RevenueTotals(_Result):
    currency: str
    invoiced: Decimal
    collected: Decimal
    invoice_count: int
    payment_count: int


class RevenueSummary(_Result):
    period_start: date
    period_end: date
    totals: list[RevenueTotals]
    has_data: bool
    definitions: str = (
        "invoiced = sum of non-void invoice totals by issue_date; "
        "collected = sum of payments received by payment date. Both inclusive of period ends."
    )


class UnpaidInvoiceRow(_Result):
    invoice_number: str
    customer_ref: str
    customer_name: str
    issue_date: date
    due_date: date
    days_overdue: int
    currency: str
    total: Decimal
    paid: Decimal
    outstanding: Decimal


class OutstandingTotal(_Result):
    currency: str
    invoice_count: int
    outstanding: Decimal


AgingBucketName = Literal["current", "1-30", "31-60", "61-90", "90+"]


class AgingBucket(_Result):
    bucket: AgingBucketName
    currency: str
    invoice_count: int
    outstanding: Decimal


class UnpaidInvoicesResult(_Result):
    as_of: date
    overdue_only: bool
    min_days_overdue: int
    customer_ref: str | None
    total_matching: int
    returned: int
    truncated: bool
    totals: list[OutstandingTotal]
    aging: list[AgingBucket]
    invoices: list[UnpaidInvoiceRow]
    definitions: str = (
        "unpaid = open invoice with outstanding balance > 0 (total minus payments); "
        "overdue = unpaid and due_date before as_of; days_overdue = as_of - due_date."
    )


class CustomerTotals(_Result):
    currency: str
    invoiced: Decimal
    collected: Decimal
    outstanding: Decimal
    overdue_outstanding: Decimal
    open_invoice_count: int
    overdue_invoice_count: int


class CustomerSummary(_Result):
    found: bool
    customer_ref: str
    as_of: date
    name: str | None = None
    industry: str | None = None
    segment: str | None = None
    country: str | None = None
    first_invoice_date: date | None = None
    last_payment_date: date | None = None
    totals: list[CustomerTotals] = []


class CustomerMatch(_Result):
    customer_ref: str
    name: str
    industry: str
    segment: str
    country: str


class CustomerSearchResult(_Result):
    query: str
    matches: list[CustomerMatch]


class MonthlyPoint(_Result):
    month: str  # YYYY-MM
    currency: str
    invoiced: Decimal
    collected: Decimal


class MonthlyTrend(_Result):
    start_month: str
    end_month: str
    has_data: bool
    points: list[MonthlyPoint]
    definitions: str = (
        "invoiced = non-void invoice totals by issue month; "
        "collected = payments by payment month. Months without activity are zero."
    )
