"""Strict allowlist of AI-callable business and document retrieval tools.

Each tool is a fixed mapping from a name to (a) a Pydantic argument model that forbids
unknown fields and bounds every value, and (b) a call into ``BusinessDataService`` or
``DocumentRetrievalService``.

There is deliberately no tool that accepts SQL, column names, sort expressions or an
``account_id``. Tenant scope comes only from the authenticated user via the services.
"""

import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy.exc import SQLAlchemyError

from app.ai.embeddings import EmbeddingError
from app.business.service import (
    MAX_RANGE_DAYS,
    MAX_SEARCH_LIMIT,
    MAX_TREND_MONTHS,
    MAX_UNPAID_LIMIT,
    BusinessDataService,
    BusinessQueryError,
)
from app.documents.schemas import PolicyCategory
from app.documents.service import (
    MAX_QUERY_LENGTH,
    MAX_TOP_K,
    DocumentQueryError,
    DocumentRetrievalService,
)

logger = logging.getLogger(__name__)

CUSTOMER_REF_PATTERN = r"^[A-Za-z0-9-]{1,32}$"
MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"
MAX_RAW_ARGUMENT_BYTES = 4096
_MIN_DATE = date(2000, 1, 1)
_MAX_DATE = date(2100, 12, 31)

SQL_BUSINESS_TOOLS: frozenset[str] = frozenset(
    {
        "get_revenue_summary",
        "list_unpaid_invoices",
        "get_customer_summary",
        "search_customers",
        "get_monthly_trend",
    }
)
DOCUMENT_RAG_TOOLS: frozenset[str] = frozenset({"search_policy_documents"})


@dataclass(frozen=True)
class ToolContext:
    business: BusinessDataService
    documents: DocumentRetrievalService | None = None


class _ToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)


class RevenueSummaryArgs(_ToolArgs):
    start_date: date = Field(description="Inclusive period start (YYYY-MM-DD).")
    end_date: date = Field(description="Inclusive period end (YYYY-MM-DD).")

    @model_validator(mode="after")
    def _check_range(self) -> "RevenueSummaryArgs":
        if not (
            _MIN_DATE <= self.start_date <= _MAX_DATE and _MIN_DATE <= self.end_date <= _MAX_DATE
        ):
            raise ValueError("dates must be between 2000-01-01 and 2100-12-31")
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        if (self.end_date - self.start_date).days > MAX_RANGE_DAYS:
            raise ValueError("date range may not exceed 3 years")
        return self


class UnpaidInvoicesArgs(_ToolArgs):
    overdue_only: bool = Field(
        description="true = only invoices past their due date; false = all unpaid invoices."
    )
    min_days_overdue: int = Field(
        default=0,
        ge=0,
        le=3650,
        description="Only invoices at least this many days past due (0 = no minimum).",
    )
    customer_ref: str | None = Field(
        default=None,
        pattern=CUSTOMER_REF_PATTERN,
        description="Optional exact customer reference such as CUST-0007, or null.",
    )
    limit: int = Field(
        default=20, ge=1, le=MAX_UNPAID_LIMIT, description="Max invoice rows to list (1-50)."
    )


class CustomerSummaryArgs(_ToolArgs):
    customer_ref: str = Field(
        pattern=CUSTOMER_REF_PATTERN,
        description="Exact customer reference such as CUST-0007. Use search_customers first "
        "if you only know the name.",
    )


class SearchCustomersArgs(_ToolArgs):
    query: str = Field(
        min_length=1, max_length=100, description="Part of a customer name or reference."
    )
    limit: int = Field(default=5, ge=1, le=MAX_SEARCH_LIMIT, description="Max matches (1-10).")


class MonthlyTrendArgs(_ToolArgs):
    months: int = Field(
        default=12, ge=1, le=MAX_TREND_MONTHS, description="Number of months to include (1-24)."
    )
    end_month: str | None = Field(
        default=None,
        pattern=MONTH_PATTERN,
        description="Last month to include as YYYY-MM, or null for the current month.",
    )


class SearchPolicyDocumentsArgs(_ToolArgs):
    query: str = Field(
        min_length=2,
        max_length=MAX_QUERY_LENGTH,
        description="Natural-language search query for company policies, terms, credit limits, "
        "collections escalation tiers, refunds, or operating procedures.",
    )
    category: PolicyCategory | None = Field(
        default=None,
        description="Optional policy category filter ('payment_terms', 'collections', 'refunds', "
        "'credit_policy', 'operating_procedures'), or null to search all categories.",
    )
    top_k: int = Field(
        default=4,
        ge=1,
        le=MAX_TOP_K,
        description="Maximum number of relevant policy chunks to retrieve (1-8).",
    )


def _expect[T: BaseModel](args: BaseModel, model: type[T]) -> T:
    if not isinstance(args, model):
        raise TypeError(f"expected {model.__name__}")
    return args


ToolHandler = Callable[[ToolContext, BaseModel], Awaitable[BaseModel]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[_ToolArgs]
    handler: ToolHandler


async def _revenue(ctx: ToolContext, raw: BaseModel) -> BaseModel:
    args = _expect(raw, RevenueSummaryArgs)
    return await ctx.business.revenue_summary(args.start_date, args.end_date)


async def _unpaid(ctx: ToolContext, raw: BaseModel) -> BaseModel:
    args = _expect(raw, UnpaidInvoicesArgs)
    return await ctx.business.unpaid_invoices(
        overdue_only=args.overdue_only,
        min_days_overdue=args.min_days_overdue,
        customer_ref=args.customer_ref,
        limit=args.limit,
    )


async def _customer(ctx: ToolContext, raw: BaseModel) -> BaseModel:
    args = _expect(raw, CustomerSummaryArgs)
    return await ctx.business.customer_summary(args.customer_ref)


async def _search(ctx: ToolContext, raw: BaseModel) -> BaseModel:
    args = _expect(raw, SearchCustomersArgs)
    return await ctx.business.search_customers(args.query, args.limit)


async def _trend(ctx: ToolContext, raw: BaseModel) -> BaseModel:
    args = _expect(raw, MonthlyTrendArgs)
    end_month: date | None = None
    if args.end_month:
        year, month = (int(part) for part in args.end_month.split("-"))
        end_month = date(year, month, 1)
    return await ctx.business.monthly_trend(args.months, end_month)


async def _search_policies(ctx: ToolContext, raw: BaseModel) -> BaseModel:
    args = _expect(raw, SearchPolicyDocumentsArgs)
    if ctx.documents is None:
        raise DocumentQueryError("Policy document retrieval is not configured for this session.")
    return await ctx.documents.search_documents(
        args.query,
        category=args.category,
        top_k=args.top_k,
    )


TOOLS: Mapping[str, ToolSpec] = MappingProxyType(
    {
        spec.name: spec
        for spec in (
            ToolSpec(
                "get_revenue_summary",
                "Invoiced revenue (non-void invoices by issue date) and collected cash "
                "(payments by payment date) for an inclusive date range, per currency.",
                RevenueSummaryArgs,
                _revenue,
            ),
            ToolSpec(
                "list_unpaid_invoices",
                "Unpaid or overdue invoices with outstanding balances, totals and aging "
                "buckets, as of today. Optionally filter by customer reference.",
                UnpaidInvoicesArgs,
                _unpaid,
            ),
            ToolSpec(
                "get_customer_summary",
                "Lifetime invoiced, collected, outstanding and overdue amounts for one "
                "customer, by exact customer reference.",
                CustomerSummaryArgs,
                _customer,
            ),
            ToolSpec(
                "search_customers",
                "Find customers by partial name or reference. Returns references for use "
                "with other tools.",
                SearchCustomersArgs,
                _search,
            ),
            ToolSpec(
                "get_monthly_trend",
                "Month-by-month invoiced revenue and collected cash for the last N months.",
                MonthlyTrendArgs,
                _trend,
            ),
            ToolSpec(
                "search_policy_documents",
                "Search official company policy documents and standard operating procedures "
                "(payment terms, late fees, payment methods, collections escalation tiers, "
                "credit limits, refunds/disputes, and AR ledger SOPs). Returns verifiable "
                "excerpts and citation IDs.",
                SearchPolicyDocumentsArgs,
                _search_policies,
            ),
        )
    }
)


@dataclass
class ToolExecution:
    """Outcome of one tool call. ``payload`` is the exact JSON returned to the model."""

    name: str
    ok: bool
    arguments: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


def _failure(
    name: str, code: str, message: str, arguments: dict[str, Any] | None = None
) -> ToolExecution:
    return ToolExecution(
        name=name,
        ok=False,
        arguments=arguments,
        error_code=code,
        error_message=message,
        payload={"ok": False, "error": {"code": code, "message": message}},
    )


def _describe_validation_error(exc: ValidationError) -> str:
    # Never echo raw input values back; report only field locations and reasons.
    parts = []
    for err in exc.errors(include_input=False, include_url=False)[:5]:
        loc = ".".join(str(p) for p in err.get("loc", ())) or "arguments"
        parts.append(f"{loc}: {err.get('msg', 'invalid')}")
    return "; ".join(parts)


async def execute_tool(
    service: BusinessDataService,
    name: str,
    raw_arguments: str,
    *,
    document_service: DocumentRetrievalService | None = None,
) -> ToolExecution:
    """Validate and execute a model-requested tool call. Never raises for bad input."""
    spec = TOOLS.get(name)
    if spec is None:
        return _failure(name[:64], "unknown_tool", "This tool is not available.")

    if len(raw_arguments.encode("utf-8")) > MAX_RAW_ARGUMENT_BYTES:
        return _failure(name, "invalid_arguments", "Arguments are too large.")
    try:
        parsed = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError:
        return _failure(name, "invalid_arguments", "Arguments must be a JSON object.")
    if not isinstance(parsed, dict):
        return _failure(name, "invalid_arguments", "Arguments must be a JSON object.")

    try:
        args = spec.args_model.model_validate(parsed)
    except ValidationError as exc:
        return _failure(name, "invalid_arguments", _describe_validation_error(exc))

    arguments = args.model_dump(mode="json")
    ctx = ToolContext(business=service, documents=document_service)
    try:
        result = await spec.handler(ctx, args)
    except (BusinessQueryError, DocumentQueryError) as exc:
        return _failure(name, "invalid_arguments", str(exc), arguments)
    except EmbeddingError as exc:
        logger.warning("tool.embedding_failed", extra={"tool": name, "error_code": exc.code})
        return _failure(
            name,
            "retrieval_unavailable",
            "Document search is temporarily unavailable.",
            arguments,
        )
    except SQLAlchemyError:
        logger.exception("tool.query_failed", extra={"tool": name})
        return _failure(name, "query_failed", "The data query failed.", arguments)

    data = result.model_dump(mode="json")
    return ToolExecution(
        name=name,
        ok=True,
        arguments=arguments,
        result=data,
        payload={"ok": True, "data": data},
    )
