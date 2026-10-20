# Orvian — AI Business Data Assistant

Reliable, secure, and maintainable AI business data assistant built for operations staff. Orvian provides grounded answers across synthetic business records (customers and invoices) and fictional internal policy documents with verified citations and explicit abstention.

> **Project Status (Phase 1 — Setup & Foundation)**: Scaffolding, strict toolchains, Alembic/Neon database session configuration, minimal health endpoints, and CI are initialized. Business logic, authentication, and RAG pipelines are planned for upcoming phases.

---

## Architecture & Technology Stack

- **Monorepo Structure**: Separated `backend/` and `frontend/` folders.
- **Backend**:
  - Python 3.12, FastAPI, Pydantic v2, Pydantic Settings
  - SQLAlchemy 2 with asyncio (`sqlalchemy[asyncio]>=2.0.36`), Alembic, psycopg 3 (`psycopg[binary,pool]>=3.2`)
  - Dependency management: `uv` with committed `backend/uv.lock`
  - Neon PostgreSQL with `pgvector` and SSL enforced (`sslmode=require`)
  - Database URLs: `DATABASE_URL` (Neon pooled endpoint for runtime queries); `DIRECT_DATABASE_URL` (Neon direct unpooled endpoint strictly required for Alembic migrations)
  - Planned Auth: Evaluated alternatives documented in `docs/AUTHENTICATION.md`
- **Frontend**:
  - React 19, TypeScript (strict mode), Vite, Tailwind CSS v4, shadcn/ui, TanStack Query (`@tanstack/react-query`)
  - Dependency management: `pnpm` exclusively (pinned in `frontend/package.json`) with committed `frontend/pnpm-lock.yaml`
- **Quality Gates**:
  - Backend: Ruff (lint & format), Mypy (strict), Pytest + pytest-asyncio
  - Frontend: ESLint, Prettier, TypeScript composite check (`tsc -b`), Vitest
  - CI: GitHub Actions workflow (`.github/workflows/ci.yml`) enforcing frozen lockfile installations.

---

## Monorepo Layout

```text
Orvian/
├── .agents/
│   └── skills/                     # Project-level skills (Antigravity & Codex discovery)
│       ├── fastapi/
│       ├── neon-postgres/
│       ├── review-change/
│       ├── shadcn/
│       └── vercel-react-best-practices/
├── .github/
│   └── workflows/
│       └── ci.yml                  # GitHub Actions CI workflow
├── backend/
│   ├── alembic/                    # Database migrations (versions/, env.py)
│   ├── alembic.ini
│   ├── app/
│   │   ├── api/v1/health.py        # Minimal health & environment status endpoint
│   │   ├── auth/README.md          # Authentication architecture specifications
│   │   ├── config.py               # Pydantic Settings (Neon SSL URLs, defaults)
│   │   ├── db/session.py           # SQLAlchemy 2 async & sync session managers
│   │   └── main.py                 # FastAPI application entrypoint
│   ├── tests/                      # Pytest unit and API test suite
│   ├── pyproject.toml              # Backend dependencies and toolchain config
│   └── uv.lock                     # Committed uv lockfile
├── frontend/
│   ├── src/
│   │   ├── lib/utils.ts            # shadcn/ui cn class merging utility
│   │   ├── test/setup.ts           # Vitest DOM test setup
│   │   ├── App.tsx                 # Starter page with API health check & React Query
│   │   ├── App.test.tsx            # Component render test
│   │   ├── index.css               # Tailwind CSS v4 @theme inline tokens
│   │   └── main.tsx                # React 19 application root
│   ├── components.json             # shadcn/ui configuration
│   ├── package.json                # Pinned pnpm dependencies
│   ├── pnpm-lock.yaml              # Committed pnpm lockfile
│   ├── tsconfig.json               # TypeScript project references root
│   ├── tsconfig.app.json           # Application TypeScript strict configuration
│   ├── tsconfig.node.json          # Vite/Node TypeScript configuration
│   └── vite.config.ts              # Vite + Tailwind v4 + Vitest configuration
├── docs/
│   ├── AUTHENTICATION.md           # Authentication evaluation & architecture
│   ├── PROJECT.md                  # Scope, phases, and MVP outcomes
│   └── REVIEW_CHECKLIST.md         # Pre-merge quality & security checklist
├── .env.example                    # Environment template with zero live credentials
├── .gitignore                      # Monorepo gitignore
├── AGENTS.md                       # Agent instructions & security invariants
└── README.md                       # Main project documentation
```

---

## Native Windows Development Setup

### 1. Prerequisites
- **Python 3.12+** & **uv** package manager (`https://docs.astral.sh/uv/`)
- **Node.js 22+** & **pnpm 10+** (`corepack enable` or `npm install -g pnpm`)
- **Neon PostgreSQL**: A Neon database project with `pgvector` extension enabled.

### 2. Environment Configuration
The repository root `.env` is the ONLY configuration file loaded by the application:
```powershell
Copy-Item .env.example .env
```
Update `.env` with your Neon PostgreSQL connection credentials:
- `DATABASE_URL`: Neon pooled connection string (must include `?sslmode=require`)
- `DIRECT_DATABASE_URL`: Neon unpooled direct connection string for Alembic migrations (must include `?sslmode=require`)

> **Important**: Never run Alembic migrations through a pooled connection. Alembic requires `DIRECT_DATABASE_URL`. Both URLs must enforce `sslmode=require` when connecting to remote/Neon hosts. Duplicate `sslmode` parameters or pooled URLs for migrations will be rejected.

---

## Backend Development

Navigate to `backend/`:
```powershell
cd backend
```

1. **Create Python 3.12 Virtual Environment & Install Dependencies**:
   ```powershell
   uv venv .venv --python 3.12
   uv sync --extra dev
   ```

2. **Run Quality Checks**:
   ```powershell
   # Linting
   uv run ruff check .

   # Code Formatting Check
   uv run ruff format --check .

   # Strict Type Checking
   uv run mypy app tests

   # Unit & Integration Tests
   uv run pytest
   ```

3. **Start Development Server**:
   ```powershell
   uv run uvicorn app.main:app --reload --port 8000
   ```
   Open `http://127.0.0.1:8000/docs` for the interactive OpenAPI documentation or `http://127.0.0.1:8000/api/v1/health` for the health check endpoint.

---

## Frontend Development

Navigate to `frontend/`:
```powershell
cd frontend
```

1. **Install Dependencies (pnpm exclusively)**:
   ```powershell
   pnpm install
   ```

2. **Run Quality Checks**:
   ```powershell
   # Linting
   pnpm run lint

   # Code Formatting Check
   pnpm run format:check

   # Strict TypeScript Check (App + Node project references)
   pnpm run typecheck

   # Unit Tests (Vitest)
   pnpm run test

   # Production Build
   pnpm run build
   ```

3. **Start Development Server**:
   ```powershell
   pnpm run dev
   ```
   Open `http://localhost:5173` in your browser.

---

## Engineering & Security Invariants
- **Synthetic Data**: All customer, invoice, and policy records are demonstrably synthetic demo data.
- **Strict Read-Only AI Access**: Database access occurs exclusively through explicit, allowlisted Python functions. Arbitrary model-generated SQL is prohibited.
- **Grounded Citations**: Document retrieval requires explicit source attribution and mandatory abstention when evidence is insufficient.
- **No Unpinned Dependencies**: Both `backend/uv.lock` and `frontend/pnpm-lock.yaml` are strictly tracked in Git.
