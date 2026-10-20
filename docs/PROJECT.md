# Orvian — Product and Engineering Scope

## Problem
Operations staff need dependable answers from structured business records and internal policy documents without hallucinations, data leakage, or unsafe database access.

## MVP Outcomes
1. Search/read synthetic customers and invoices via allowlisted read-only backend functions.
2. Retrieve policy-document excerpts and return source-aware answers with verified citations (including meaningful refusal/abstention when no evidence exists).
3. Provide a clean dashboard with question input, answer view, verifiable citations, query telemetry (latency + estimated cost), and history for the demo.
4. Measure a reproducible evaluation set, tracking latency, approximate model cost, and adversarial safety.
5. Authenticate users safely with email/password, email verification, Google OAuth, password reset, server-side session management, and rate limiting (post-setup phase).

## Initial Data
Synthetic customers and invoices, plus a curated set of fictional policy documents. All records demonstrably synthetic.

## Non-Goals
No autonomous write actions, production financial advice, unrestricted SQL, public web browsing, outbound email execution without explicit confirmation, broad uncontrolled multi-agent autonomy, unverified compliance claims, or unpinned lockfiles.

## Architecture & Technology Stack
- **Monorepo**: Backend in `backend/`, frontend in `frontend/`, shared docs in `docs/`, E2E tests in `e2e/`.
- **Backend**: Python 3.12, FastAPI, Pydantic v2, Pydantic Settings, SQLAlchemy 2 async, Alembic, psycopg 3 (`psycopg[binary,pool]>=3.2`).
  - Package manager: `uv` with `pyproject.toml` and committed `uv.lock`.
- **Database**: Neon PostgreSQL with `pgvector` and SSL enforced (`sslmode=require`).
  - Runtime pool: `DATABASE_URL` (Neon pooled endpoint).
  - Migration connection: `DIRECT_DATABASE_URL` (Neon unpooled direct endpoint for Alembic).
- **Frontend**: React 19, TypeScript (strict mode), Vite, Tailwind CSS v4, shadcn/ui, TanStack Query (`@tanstack/react-query`).
  - Package manager: `pnpm` exclusively, version-pinned in `package.json` with committed `pnpm-lock.yaml`.
- **Authentication (Planned for Post-Setup)**:
  - Email/password with mandatory verification, Google OAuth2, password reset, secure session management with server-side revocation, account-level authorization, and rate limiting.
  - Evaluation of alternatives to maintenance-mode FastAPI Users: prefer proven libraries (e.g. Authlib + pwdlib[argon2] + PyJWT + DB session table) or managed identity providers (e.g. Clerk / Supabase Auth) over custom security protocols.
- **Local Development**: Native Windows with Python, Node.js, pnpm, and Neon PostgreSQL over SSL. Docker is optional for future deployment.

## Project Conventions
- Backend in `backend/`, frontend in `frontend/`, shared docs in `docs/`, E2E tests in `e2e/`.
- Committed lockfiles: `backend/uv.lock` and `frontend/pnpm-lock.yaml`. Never commit `package-lock.json`.
- Strict typing: `mypy` strict mode for Python, `tsc --noEmit` with strict null checks for TypeScript.
- Comprehensive `.env.example` templates with zero live secrets.

## Phases
1. **Scaffold, Quality Gates & Database Foundation** (Current Phase):
   - Monorepo structure, toolchain configuration (`uv`, `pnpm`), strict linting, typechecking, testing scaffolds, Neon PostgreSQL SSL session setup, Alembic configuration, and minimal health endpoints.
2. **Authentication & Account Authorization**:
   - Production-ready auth implementation based on evaluated alternative, email verification, Google OAuth, session revocation, and route guards.
3. **Read-Only AI Tool Integration**:
   - Allowlisted parameterized query tools for synthetic customers and invoices, read-only transaction enforcement.
4. **Document Ingestion & Grounded Retrieval**:
   - Validated file upload (.md/.txt), pgvector chunking and embedding, citation-backed assistant orchestration with strict abstention and prompt injection defense.
5. **Evaluation, Telemetry & Safety Benchmark**:
   - Reproducible evaluation suite, cost/latency tracking, adversarial prompt injection tests.
6. **Responsive Frontend Dashboard & CI Polish**:
   - Accessible UI with shadcn/ui, TanStack Query integration, citation cards, mobile responsiveness, and GitHub Actions CI.
