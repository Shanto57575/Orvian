"""Reproducible, idempotent policy document ingestion CLI for Brightline Supply Co.

Usage (from backend/):
    uv run python -m scripts.seed_documents
    uv run python -m scripts.seed_documents --dry-run
    uv run python -m scripts.seed_documents --force
    uv run python -m scripts.seed_documents --deterministic

Guarantees:
- Idempotent: skips documents whose SHA-256 checksum matches the database row unless --force.
- Account-scoped: ingests into the target account (defaults to demo-brightline-supply).
- Refuses to run when ENVIRONMENT=production.
"""

import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import (
    DeterministicEmbeddingClient,
    EmbeddingClient,
    OpenAIEmbeddingClient,
)
from app.config import get_settings
from app.db.models import Account
from app.documents.ingestion import (
    DEFAULT_POLICIES_DIR,
    IngestionSummary,
    ingest_policy_documents,
)
from scripts.seed_business_data import (
    DEMO_ACCOUNT_NAME,
    DEMO_ACCOUNT_SLUG,
    DEMO_CURRENCY,
)

_NAMESPACE = uuid.UUID("6f1c2a52-4d0e-4c39-9a57-0f2f6d1e8b10")


class DocumentSeedError(ValueError):
    """Raised when document seeding cannot proceed safely."""


def _build_embedder(*, deterministic: bool = False) -> EmbeddingClient:
    settings = get_settings()
    if deterministic or not settings.OPENAI_API_KEY:
        return DeterministicEmbeddingClient(dimensions=settings.EMBEDDING_DIMENSIONS)
    return OpenAIEmbeddingClient(
        api_key=settings.OPENAI_API_KEY,
        model=settings.EMBEDDING_MODEL,
        dimensions=settings.EMBEDDING_DIMENSIONS,
        timeout_seconds=float(settings.LLM_TIMEOUT_SECONDS),
        max_retries=settings.LLM_MAX_RETRIES,
    )


async def seed_demo_documents(
    session: AsyncSession,
    *,
    embedder: EmbeddingClient | None = None,
    account_slug: str = DEMO_ACCOUNT_SLUG,
    policies_dir: Path = DEFAULT_POLICIES_DIR,
    force: bool = False,
) -> IngestionSummary:
    """Ensure the demo account exists and ingest the policy document corpus."""
    account = (
        await session.execute(select(Account).where(Account.slug == account_slug))
    ).scalar_one_or_none()
    if account is None:
        if account_slug != DEMO_ACCOUNT_SLUG:
            raise DocumentSeedError(f"Account '{account_slug}' does not exist.")
        account = Account(
            id=uuid.uuid5(_NAMESPACE, f"account:{DEMO_ACCOUNT_SLUG}"),
            name=DEMO_ACCOUNT_NAME,
            slug=DEMO_ACCOUNT_SLUG,
            is_demo=True,
            currency=DEMO_CURRENCY,
        )
        session.add(account)
        await session.flush()
    elif not account.is_demo:
        raise DocumentSeedError(f"Account '{account_slug}' exists but is not a demo account.")

    active_embedder = embedder or _build_embedder()
    return await ingest_policy_documents(
        session,
        account_id=account.id,
        embedder=active_embedder,
        policies_dir=policies_dir,
        force=force,
    )


async def _main(args: argparse.Namespace) -> int:
    from app.db.session import AsyncSessionLocal, async_engine

    settings = get_settings()
    if settings.ENVIRONMENT == "production":
        print("Refusing to seed synthetic documents with ENVIRONMENT=production.", file=sys.stderr)
        return 2

    embedder = _build_embedder(deterministic=args.deterministic)
    try:
        async with AsyncSessionLocal() as session:
            try:
                summary = await seed_demo_documents(
                    session,
                    embedder=embedder,
                    account_slug=args.account_slug,
                    force=args.force,
                )
                if args.dry_run:
                    await session.rollback()
                else:
                    await session.commit()
            except Exception:
                await session.rollback()
                raise
    except DocumentSeedError as exc:
        print(f"Document seed aborted: {exc}", file=sys.stderr)
        return 1
    finally:
        await async_engine.dispose()

    mode = "DRY RUN (rolled back)" if args.dry_run else "committed"
    print(
        f"Documents {mode}: account={summary.account_id} embedder={embedder.model} "
        f"processed={summary.documents_processed} updated={summary.documents_updated} "
        f"skipped={summary.documents_skipped} chunks={summary.chunks_written} "
        f"embedding_tokens={summary.embedding_tokens}"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest Orvian fictional company policy documents."
    )
    parser.add_argument("--account-slug", default=DEMO_ACCOUNT_SLUG)
    parser.add_argument("--force", action="store_true", help="Re-embed even if checksum matches.")
    parser.add_argument(
        "--deterministic",
        action="store_true",
        help="Use offline deterministic embeddings instead of OpenAI API.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Ingest and roll back.")
    args = parser.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raise SystemExit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
