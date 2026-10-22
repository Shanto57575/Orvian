# Orvian Business Data Foundation & AI Tool Calling

## Overview
Day 4 introduces the first working AI Operations Analyst for Orvian:
- An isolated account/tenant layer separating customer and financial records.
- Deterministic synthetic business data (40 customers, ~480 invoices, ~480 payments).
- Strongly typed, read-only business services computing revenue, overdue balances, aging buckets, and customer summaries.
- Strictly defined AI tools that invoke business services with Pydantic validation (zero arbitrary SQL).
- A protected `/api/v1/chat` endpoint orchestrating OpenAI `gpt-4o-mini` with bounded tool execution and safe fallbacks.

## Architecture

```
User -> /api/v1/chat (FastAPI)
          |
          +--> Auth Guards: require_verified_user, validate_csrf, rate limiter
          +--> Safe Check: account_id is None -> returns no_data immediately
          +--> Read-Only DB Session: SET TRANSACTION READ ONLY (PostgreSQL)
          +--> Orchestrator (run_chat):
                 |
                 +--> OpenAIChatClient (gpt-4o-mini, temp=0, strict=True)
                 +--> Tool Dispatcher:
                        - get_revenue_summary
                        - list_unpaid_invoices
                        - get_customer_summary
                        - search_customers
                        - get_monthly_trend
                 +--> BusinessDataService:
                        - Scoped to user's account_id
                        - Integer cent arithmetic (BigInteger)
                        - Parameterized SQLAlchemy Core
```

## Data Model

- **`accounts`**: Tenant boundary (`id`, `name`, `slug`, `is_demo`, `currency`, `created_at`).
- **`users`**: Added nullable `account_id` foreign key with `ON DELETE SET NULL`. Users without an account are safely served empty answers without LLM invocation.
- **`customers`**: Synthetic accounts-receivable customers (`external_ref`, `name`, `email`, `industry`, `country`, `segment`).
  - Constraint: `UNIQUE(account_id, external_ref)` and `UNIQUE(account_id, id)`.
- **`invoices`**: Accounts-receivable invoices (`invoice_number`, `issue_date`, `due_date`, `currency`, `subtotal_cents`, `tax_cents`, `total_cents`, `status`).
  - Constraint: Composite foreign key `FOREIGN KEY(account_id, customer_id) REFERENCES customers(account_id, id)` ensures cross-tenant invoice linkage is rejected at the database level.
  - Checks: `subtotal_cents >= 0`, `tax_cents >= 0`, `total_cents = subtotal_cents + tax_cents`, `due_date >= issue_date`, `status IN ('open', 'paid', 'void')`.
- **`payments`**: Applied cash payments (`amount_cents`, `paid_on`, `method`).
  - Constraint: Composite foreign key `FOREIGN KEY(account_id, invoice_id) REFERENCES invoices(account_id, id)`.
  - Checks: `amount_cents > 0`, `method IN ('bank_transfer', 'card', 'ach', 'check')`.

## Synthetic Data Seeding

The seed script (`backend/scripts/seed_business_data.py`) provides idempotent, deterministic synthetic data for one fictional business ("Brightline Supply Co."):
- Uses a fixed seed (default `42`) and anchor date (default `2026-10-15`).
- Produces identical UUID5 identifiers and row counts across runs.
- Replaces existing demo rows for that slug without deleting authentication data or other tenants.
- Demo access is assigned exclusively to an explicitly passed verified user via `--member`.

### Seeding Commands (from `backend/`):
```bash
# Dry run verification
uv run python -m scripts.seed_business_data --dry-run

# Seed and link to a verified user account
uv run python -m scripts.seed_business_data --member you@example.com
```

## Approved AI Tools

| Tool Name | Purpose | Parameters |
|-----------|---------|------------|
| `get_revenue_summary` | Invoiced revenue vs collected cash by currency for a date range | `start_date`, `end_date` |
| `list_unpaid_invoices` | Open/overdue invoices, aging breakdown (1-30, 31-60, 61-90, 90+), totals | `overdue_only`, `min_days_overdue`, `customer_ref`, `limit` (max 50) |
| `get_customer_summary` | Customer lifetime invoiced, collected, outstanding, and overdue amounts | `customer_ref` |
| `search_customers` | Search customers by name or reference substring | `query` (max 100 chars), `limit` (max 10) |
| `get_monthly_trend` | Month-by-month invoiced and collected totals | `months` (max 24), `end_month` |

## Safety & Invariants

1. **No Model SQL**: The model cannot provide SQL queries, table names, or raw filters. Every report is executed through precompiled SQLAlchemy expressions.
2. **Account Isolation**: `account_id` is supplied exclusively by the authenticated user's session and injected into `BusinessDataService`. AI tool arguments forbid `account_id`.
3. **Integer Cents**: All money columns and calculations use exact integer cents to eliminate floating-point inaccuracies. Formatted as `Decimal` strings in API outputs.
4. **Bounded Iterations**: Orchestration caps at `LLM_MAX_TOOL_ITERATIONS=4` and `LLM_MAX_TOOL_CALLS=8`.
5. **Anti-Hallucination**: If the model proposes an answer containing monetary numbers without executing tools, the response is replaced with a safe refusal.
6. **Production Protection**: The seed script refuses execution if `ENVIRONMENT=production`.
