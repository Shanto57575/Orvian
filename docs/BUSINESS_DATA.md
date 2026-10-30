# Orvian Business Data Foundation, Document RAG & Hybrid AI Tool Calling

## Overview
Orvian provides an AI Operations Analyst combining structured financial records with account-scoped company policy documents:
- An isolated account/tenant layer separating customer, financial, and policy document records.
- Deterministic synthetic business data (40 customers, ~480 invoices, ~480 payments).
- Five fictional company policy documents (~20 chunks) stored in Neon PostgreSQL with `pgvector` embeddings (`text-embedding-3-small`, 1536 dimensions).
- Strongly typed, read-only business and document retrieval services.
- Six strictly defined AI tools (5 SQL business tools + 1 policy RAG tool) with Pydantic validation and zero arbitrary SQL.
- A protected `/api/v1/chat` endpoint orchestrating OpenAI `gpt-4o-mini` with bounded tool execution, verified citations, and safe fallbacks.

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
                        - get_revenue_summary       (SQL)
                        - list_unpaid_invoices      (SQL)
                        - get_customer_summary      (SQL)
                        - search_customers          (SQL)
                        - get_monthly_trend         (SQL)
                        - search_policy_documents   (pgvector RAG)
                 +--> BusinessDataService & DocumentRetrievalService:
                        - Scoped to user's account_id
                        - Integer cent arithmetic (BigInteger)
                        - Parameterized SQLAlchemy Core + pgvector cosine distance
                 +--> Citation & Grounding Verifier:
                        - Strips unverified citation tags
                        - Blocks ungrounded monetary or record claims
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
- **`policy_documents`**: Account-scoped company policy documents (`doc_key`, `title`, `category`, `version`, `effective_date`, `filename`, `checksum_sha256`).
  - Constraint: `UNIQUE(account_id, doc_key)` and `UNIQUE(account_id, id)`.
- **`document_chunks`**: Section-level chunks with pgvector embeddings (`chunk_id`, `chunk_index`, `section_title`, `page_number`, `content`, `token_count`, `embedding VECTOR(1536)`).
  - Constraint: Composite foreign key `FOREIGN KEY(account_id, document_id) REFERENCES policy_documents(account_id, id)` and `HNSW (embedding vector_cosine_ops)` index.

## Synthetic Data & Document Seeding

1. **Business Data Seed (`backend/scripts/seed_business_data.py`)**:
   - Uses a fixed seed (default `42`) and anchor date (default `2026-10-15`).
   - Produces identical UUID5 identifiers and row counts across runs.
2. **Policy Document Seed (`backend/scripts/seed_documents.py`)**:
   - Parses the 5 Markdown policy documents in `backend/data/policies/`, chunks by section, generates embeddings, and upserts idempotently using `checksum_sha256`.

### Seeding Commands (from `backend/`):
```bash
# Seed business records and link to a verified user account
uv run python -m scripts.seed_business_data --member you@example.com

# Ingest company policy documents into the demo account
uv run python -m scripts.seed_documents
```

## Approved AI Tools

| Tool Name | Purpose | Parameters |
|-----------|---------|------------|
| `get_revenue_summary` | Invoiced revenue vs collected cash by currency for a date range | `start_date`, `end_date` |
| `list_unpaid_invoices` | Open/overdue invoices, aging breakdown (1-30, 31-60, 61-90, 90+), totals | `overdue_only`, `min_days_overdue`, `customer_ref`, `limit` (max 50) |
| `get_customer_summary` | Customer lifetime invoiced, collected, outstanding, and overdue amounts | `customer_ref` |
| `search_customers` | Search customers by name or reference substring | `query` (max 100 chars), `limit` (max 10) |
| `get_monthly_trend` | Month-by-month invoiced and collected totals | `months` (max 24), `end_month` |
| `search_policy_documents` | Semantic + lexical search over account-scoped company policy documents | `query` (max 300 chars), `category`, `top_k` (max 8) |

## Safety & Invariants

1. **No Model SQL**: The model cannot provide SQL queries, table names, or raw filters. Every report is executed through precompiled SQLAlchemy expressions.
2. **Account Isolation**: `account_id` is supplied exclusively by the authenticated user's session and injected into `BusinessDataService` and `DocumentRetrievalService`. AI tool arguments forbid `account_id`.
3. **Integer Cents**: All money columns and calculations use exact integer cents to eliminate floating-point inaccuracies. Formatted as `Decimal` strings in API outputs.
4. **Bounded Iterations & Tokens**: Orchestration caps at `LLM_MAX_TOOL_ITERATIONS=5`, `LLM_MAX_TOOL_CALLS=8`, and `LLM_MAX_INPUT_TOKENS_PER_REQUEST=16000`.
5. **Anti-Hallucination & Citation Verification**: Any answer claiming account-specific monetary figures or invoice/customer IDs without executing SQL tools is replaced with a safe refusal, and any citation tag not present in the turn's retrieved chunks is stripped.
6. **Production Protection**: Both seed scripts refuse execution if `ENVIRONMENT=production`.
