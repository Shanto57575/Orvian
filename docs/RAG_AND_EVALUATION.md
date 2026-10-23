# Orvian Document RAG & Hybrid Evaluation Guide

## 1. Policy Knowledge Base (`backend/data/policies/`)

Orvian includes five synthetic policy documents for **Brightline Supply Co.** designed to pair directly with the structured accounts-receivable ledger:

| `doc_key` | Filename | Category | Version | Key Thresholds & Rules |
|---|---|---|---|---|
| `DOC-PAY-TERMS` | `01_payment_terms_policy.md` | `payment_terms` | `v2.1` | `smb`: Net 30; `mid_market`: Net 30; `enterprise`: Net 45; 5-day grace period; 1.5%/mo late fee after 15 days overdue; paper `check` cap `10,000.00 USD`; `enterprise` must use `ach` or `bank_transfer`; crypto/cash prohibited. |
| `DOC-COLLECTIONS` | `02_collections_and_escalation_sop.md` | `collections` | `v1.4` | Aging buckets mapped to escalation tiers: Tier 1 (`1-30` days), Tier 2 (`31-60` days, Soft Credit Hold at Day 31), Tier 3 (`61-90` days, Hard Shipment Hold at Day 61 + demand notice $\ge$ `5,000.00 USD`), Tier 4 (`90+` days, external collections $\ge$ `10,000.00 USD`, small-balance write-off review `< 1,000.00 USD`). |
| `DOC-REFUNDS` | `03_refunds_and_disputes_policy.md` | `refunds` | `v1.2` | 15-day billing dispute window from `issue_date`; 30-day defective goods RMA window (15% restocking fee for discretionary returns); cash refund eligibility $\ge$ `500.00 USD`; approval matrix: AR Manager ($\le$ `2,500.00 USD`), Controller/VP Finance (`2,500.01`–`25,000.00 USD`), CFO ($>$ `25,000.00 USD`). |
| `DOC-CREDIT` | `04_credit_risk_and_limits_policy.md` | `credit_policy` | `v2.0` | Aggregate open credit limits: `smb` = `15,000.00 USD`, `mid_market` = `50,000.00 USD`, `enterprise` = `200,000.00 USD`; automatic credit suspension if `outstanding > 100%` of limit, `overdue_outstanding > 50%` of limit, or any single open invoice is $> 60$ days overdue. |
| `DOC-OPS-SOP` | `05_ar_operating_procedures.md` | `operating_procedures` | `v1.3` | Integer cent accounting; 8.0% standard sales tax; payment posting SLAs (24h ACH/wire/card, 3 business days check); void eligibility (`paid == 0.00 USD`, within 30 days of `issue_date`, Controller sign-off). |

---

## 2. Retrieval Architecture

1. **Chunking (`app/documents/chunker.py`)**:
   - Parses YAML frontmatter, `<!-- page: N -->` markers, and `## Section` headings.
   - Assigns stable, human-verifiable chunk identifiers (`DOC-COLLECTIONS#C01` through `#C04`).
   - Prepends `[Document Title (version) — Section Title]` to each chunk's body so embeddings capture document and section context.
2. **Embeddings (`app/ai/embeddings.py`)**:
   - Production runtime uses `OpenAIEmbeddingClient` (`text-embedding-3-small`, `1536` dimensions, `encoding_format="float"`).
   - Tests and offline evaluations use `DeterministicEmbeddingClient` (unit-normalized domain concept clusters + unigram/bigram SHA-256 feature hashing) requiring zero API credits.
3. **Tenant-Isolated Vector + Lexical Hybrid Search (`app/documents/service.py`)**:
   - `DocumentRetrievalService` binds `account_id` at construction time from the authenticated user's session.
   - Queries filter `DocumentChunk.account_id == account_id` and `PolicyDocument.account_id == account_id` (enforced at the schema level by a composite foreign key).
   - Computes cosine distance (`<=>` via `pgvector` HNSW index on PostgreSQL) combined with a bounded lexical overlap boost (`[0.0, 0.18]`) for exact policy identifiers and domain terms, rejecting results above `RAG_MAX_COSINE_DISTANCE` (default `0.58`).

---

## 3. Evaluation Framework (`app/evals/` & `scripts/run_evals.py`)

The evaluation suite (`backend/app/evals/cases.py`) contains **24 representative evaluation cases** across 8 categories:
- **`sql_only` (3 cases)**: `SQL-01` through `SQL-03`
- **`doc_only` (4 cases)**: `DOC-01` through `DOC-04`
- **`hybrid_sql_rag` (4 cases)**: `HYB-01` through `HYB-04`
- **`missing_evidence` (3 cases)**: `MISS-01` through `MISS-03`
- **`contradictory_evidence` (2 cases)**: `CONTRA-01`, `CONTRA-02`
- **`cross_account_isolation` (2 cases)**: `ISO-01`, `ISO-02`
- **`prompt_injection` (3 cases)**: `INJ-01` through `INJ-03`
- **`tool_and_grounding_guards` (3 cases)**: `GUARD-01` through `GUARD-03`

Total: **24 cases in `EVAL_CASES`**.

### Running Evaluations (from `backend/`):
```bash
# Standard deterministic evaluation (0 API credits, runs in pytest and CLI)
uv run python -m scripts.run_evals

# Live OpenAI LLM + Embedding evaluation (requires OPENAI_API_KEY in backend/.env)
uv run python -m scripts.run_evals --live --output-json eval_report.json
```

### Known Limitations & Trade-Offs
- **Chunk Granularity**: Policy documents are chunked by `## Section` (~100–250 words). Very long multi-page tables in future corpora would benefit from table-aware splitting.
- **Grounding Guard Scope**: `looks_ungrounded` blocks any answer that cites monetary figures or invoice/customer IDs when no SQL tool succeeded, unless those exact figures appear in the retrieved policy excerpts. It does not perform full theorem-proving over arithmetic derived by the LLM; users can expand the `Tool Call` and `Verified Policy Citations` drawers in the UI to inspect the exact underlying database rows and policy excerpts.
