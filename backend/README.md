# Orvian Backend

FastAPI backend with SQLAlchemy 2, Alembic, psycopg 3, Neon PostgreSQL with pgvector, and Pydantic v2.

## Local Setup (Native Windows)

1. Ensure `uv` is installed (`Get-Command uv`).
2. Create and sync the virtual environment:
   ```powershell
   cd backend
   uv venv .venv --python 3.12
   uv sync --extra dev
   ```
3. Environment configuration:
   The backend loads configuration from the **`backend/.env`** file.
   ```powershell
   # In the backend directory:
   Copy-Item .env.example .env
   ```
   Never commit `.env` to version control.
4. Run checks:
   ```powershell
   uv run ruff check .
   uv run ruff format --check .
   uv run mypy app tests
   uv run pytest
   ```
5. Run development server:
   ```powershell
   uv run uvicorn app.main:app --reload --port 8000
   ```
