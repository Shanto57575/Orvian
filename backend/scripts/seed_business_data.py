"""Reproducible, idempotent synthetic business data seed for one fictional demo company.

Usage (from backend/):
    uv run python -m scripts.seed_business_data --member you@example.com
    uv run python -m scripts.seed_business_data --seed 42 --anchor-date 2026-10-15 --dry-run

Guarantees:
- Deterministic: same ``--seed`` and ``--anchor-date`` always produce identical rows and IDs.
- Idempotent: re-running replaces only the demo account's customers/invoices/payments inside
  one transaction. Users, sessions and other auth data are never deleted.
- Demo access is granted only to the explicitly named, verified, active user (``--member``).
- Refuses to run when ENVIRONMENT=production.

All names, emails (``@example.com``) and amounts are fictional.
"""

import argparse
import asyncio
import random
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Account, Customer, Invoice, Payment, User

DEMO_ACCOUNT_SLUG = "demo-brightline-supply"
DEMO_ACCOUNT_NAME = "Brightline Supply Co. (Synthetic Demo)"
DEMO_CURRENCY = "USD"
DEFAULT_SEED = 42
DEFAULT_ANCHOR = date(2026, 10, 15)
HISTORY_MONTHS = 18
CUSTOMER_COUNT = 40
TAX_RATE_PERCENT = 8
_NAMESPACE = uuid.UUID("6f1c2a52-4d0e-4c39-9a57-0f2f6d1e8b10")

_PREFIXES = [
    "Aster",
    "Bluefield",
    "Cedar",
    "Driftwood",
    "Ember",
    "Foxglove",
    "Granite",
    "Harbor",
    "Ironwood",
    "Juniper",
    "Keystone",
    "Lumen",
    "Maple",
    "Northgate",
    "Oakridge",
    "Pinecrest",
    "Quarry",
    "Redwood",
    "Silverline",
    "Tidewater",
    "Upland",
    "Vantage",
    "Willow",
    "Zenith",
]
_SUFFIXES = [
    "Logistics",
    "Dental Group",
    "Hospitality",
    "Builders",
    "Analytics",
    "Foods",
    "Clinics",
    "Manufacturing",
    "Retail",
    "Studios",
    "Engineering",
    "Outfitters",
]
_INDUSTRIES = {
    "Logistics": "Transportation",
    "Dental Group": "Healthcare",
    "Hospitality": "Hospitality",
    "Builders": "Construction",
    "Analytics": "Software",
    "Foods": "Food & Beverage",
    "Clinics": "Healthcare",
    "Manufacturing": "Manufacturing",
    "Retail": "Retail",
    "Studios": "Media",
    "Engineering": "Professional Services",
    "Outfitters": "Retail",
}
_COUNTRIES = ["US", "US", "US", "US", "CA", "GB", "AU"]
# segment -> (weight, invoice probability per month, base subtotal cents, payment terms days)
_SEGMENTS: dict[str, tuple[int, float, int, int]] = {
    "smb": (55, 0.65, 180_000, 30),
    "mid_market": (32, 0.80, 650_000, 30),
    "enterprise": (13, 0.90, 2_400_000, 45),
}
# payer profile -> (weight, min delay days, max delay days, probability of never paying)
_PAYERS: dict[str, tuple[int, int, int, float]] = {
    "prompt": (35, 0, 20, 0.0),
    "typical": (40, 10, 45, 0.02),
    "late": (18, 30, 95, 0.05),
    "delinquent": (7, 60, 150, 0.45),
}
_METHODS = {
    "smb": ["card", "card", "ach", "check"],
    "mid_market": ["ach", "bank_transfer", "card"],
    "enterprise": ["bank_transfer", "ach"],
}
# Mild seasonality: stronger Q4, softer summer.
_SEASONALITY = {
    1: 0.95,
    2: 0.9,
    3: 1.0,
    4: 1.0,
    5: 1.0,
    6: 0.92,
    7: 0.88,
    8: 0.9,
    9: 1.02,
    10: 1.08,
    11: 1.15,
    12: 1.2,
}


@dataclass(frozen=True)
class SeedReport:
    account_id: uuid.UUID
    customers: int
    invoices: int
    payments: int
    member_email: str | None


class SeedError(RuntimeError):
    """Raised when seeding preconditions are not met."""


def _uid(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"{DEMO_ACCOUNT_SLUG}:{kind}:{key}")


def _weighted(rng: random.Random, table: dict[str, Any]) -> str:
    names = list(table)
    return rng.choices(names, weights=[table[n][0] for n in names], k=1)[0]


def _month_start(d: date, delta: int) -> date:
    index = d.year * 12 + (d.month - 1) + delta
    return date(index // 12, index % 12 + 1, 1)


def _timestamp(d: date) -> datetime:
    return datetime.combine(d, time(9, 0), tzinfo=UTC)


def generate_dataset(
    seed: int, anchor: date, account_id: uuid.UUID
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Pure, deterministic generation of customer, invoice and payment rows."""
    rng = random.Random(seed)
    first_month = _month_start(anchor, -(HISTORY_MONTHS - 1))

    names = [f"{p} {s}" for p in _PREFIXES for s in _SUFFIXES]
    rng.shuffle(names)

    customers: list[dict[str, Any]] = []
    profiles: dict[str, tuple[str, str]] = {}
    for i in range(CUSTOMER_COUNT):
        ref = f"CUST-{i + 1:04d}"
        name = names[i]
        suffix = next(s for s in _SUFFIXES if name.endswith(s))
        segment = _weighted(rng, _SEGMENTS)
        payer = _weighted(rng, _PAYERS)
        profiles[ref] = (segment, payer)
        slug = name.lower().replace(" ", "-").replace("&", "and")
        customers.append(
            {
                "id": _uid("customer", ref),
                "account_id": account_id,
                "external_ref": ref,
                "name": name,
                "email": f"ap@{slug}.example.com",
                "industry": _INDUSTRIES[suffix],
                "country": rng.choice(_COUNTRIES),
                "segment": segment,
                "created_at": _timestamp(first_month - timedelta(days=rng.randint(10, 400))),
            }
        )

    drafts: list[tuple[date, str, int]] = []
    for customer in customers:
        ref = customer["external_ref"]
        segment, _ = profiles[ref]
        _, probability, base, _ = _SEGMENTS[segment]
        size = rng.uniform(0.6, 1.6)
        for m in range(HISTORY_MONTHS):
            month = _month_start(first_month, m)
            if rng.random() > probability:
                continue
            issue = month + timedelta(days=rng.randint(0, 27))
            if issue > anchor:
                continue
            subtotal = int(base * size * _SEASONALITY[month.month] * rng.uniform(0.75, 1.25))
            subtotal = max(5_000, subtotal - subtotal % 100)  # whole dollars
            drafts.append((issue, ref, subtotal))
    drafts.sort(key=lambda d: (d[0], d[1]))

    invoices: list[dict[str, Any]] = []
    payments: list[dict[str, Any]] = []
    for seq, (issue, ref, subtotal) in enumerate(drafts, start=1):
        segment, payer = profiles[ref]
        terms = _SEGMENTS[segment][3]
        _, min_delay, max_delay, never_pay = _PAYERS[payer]
        number = f"INV-{seq:06d}"
        invoice_id = _uid("invoice", number)
        tax = (subtotal * TAX_RATE_PERCENT + 50) // 100
        total = subtotal + tax
        due = issue + timedelta(days=terms)
        status = "open"

        if rng.random() < 0.02:
            status = "void"
        elif rng.random() >= never_pay:
            pay_date = issue + timedelta(days=rng.randint(min_delay, max_delay))
            method = rng.choice(_METHODS[segment])
            if rng.random() < 0.15:
                # Two installments: a partial first payment, then the remainder.
                first_amount = (total * rng.randint(30, 60)) // 100
                first_date = issue + timedelta(days=(pay_date - issue).days // 2)
                if first_date <= anchor:
                    payments.append(
                        {
                            "id": _uid("payment", f"{number}:1"),
                            "account_id": account_id,
                            "invoice_id": invoice_id,
                            "amount_cents": first_amount,
                            "paid_on": first_date,
                            "method": method,
                            "created_at": _timestamp(first_date),
                        }
                    )
                    if pay_date <= anchor:
                        payments.append(
                            {
                                "id": _uid("payment", f"{number}:2"),
                                "account_id": account_id,
                                "invoice_id": invoice_id,
                                "amount_cents": total - first_amount,
                                "paid_on": pay_date,
                                "method": method,
                                "created_at": _timestamp(pay_date),
                            }
                        )
                        status = "paid"
            elif pay_date <= anchor:
                payments.append(
                    {
                        "id": _uid("payment", f"{number}:1"),
                        "account_id": account_id,
                        "invoice_id": invoice_id,
                        "amount_cents": total,
                        "paid_on": pay_date,
                        "method": method,
                        "created_at": _timestamp(pay_date),
                    }
                )
                status = "paid"

        invoices.append(
            {
                "id": invoice_id,
                "account_id": account_id,
                "customer_id": _uid("customer", ref),
                "invoice_number": number,
                "issue_date": issue,
                "due_date": due,
                "currency": DEMO_CURRENCY,
                "subtotal_cents": subtotal,
                "tax_cents": tax,
                "total_cents": total,
                "status": status,
                "created_at": _timestamp(issue),
            }
        )
    return customers, invoices, payments


async def seed_demo_data(
    session: AsyncSession,
    *,
    seed: int = DEFAULT_SEED,
    anchor: date = DEFAULT_ANCHOR,
    member_email: str | None = None,
) -> SeedReport:
    """Idempotently (re)create the demo account's business data. Caller commits."""
    account = (
        await session.execute(select(Account).where(Account.slug == DEMO_ACCOUNT_SLUG))
    ).scalar_one_or_none()
    if account is None:
        account = Account(
            id=_uid("account", DEMO_ACCOUNT_SLUG),
            name=DEMO_ACCOUNT_NAME,
            slug=DEMO_ACCOUNT_SLUG,
            is_demo=True,
            currency=DEMO_CURRENCY,
        )
        session.add(account)
        await session.flush()
    elif not account.is_demo:
        raise SeedError(f"Account '{DEMO_ACCOUNT_SLUG}' exists but is not a demo account.")

    member: User | None = None
    if member_email:
        member = (
            await session.execute(
                select(User).where(func.lower(User.email) == member_email.strip().lower())
            )
        ).scalar_one_or_none()
        if member is None:
            raise SeedError("Member user not found. Register and verify the user first.")
        if not member.is_verified or not member.is_active:
            raise SeedError("Member user must be verified and active.")
        if member.account_id is not None and member.account_id != account.id:
            raise SeedError("Member user is already linked to a different account.")

    customers, invoices, payments = generate_dataset(seed, anchor, account.id)

    # Replace only this demo account's business rows (children first).
    await session.execute(delete(Payment).where(Payment.account_id == account.id))
    await session.execute(delete(Invoice).where(Invoice.account_id == account.id))
    await session.execute(delete(Customer).where(Customer.account_id == account.id))
    await session.execute(insert(Customer), customers)
    if invoices:
        await session.execute(insert(Invoice), invoices)
    if payments:
        await session.execute(insert(Payment), payments)

    if member is not None:
        member.account_id = account.id

    return SeedReport(
        account_id=account.id,
        customers=len(customers),
        invoices=len(invoices),
        payments=len(payments),
        member_email=member.email if member else None,
    )


async def _main(args: argparse.Namespace) -> int:
    from app.db.session import AsyncSessionLocal, async_engine

    settings = get_settings()
    if settings.ENVIRONMENT == "production":
        print("Refusing to seed synthetic data with ENVIRONMENT=production.", file=sys.stderr)
        return 2
    try:
        async with AsyncSessionLocal() as session:
            try:
                report = await seed_demo_data(
                    session, seed=args.seed, anchor=args.anchor_date, member_email=args.member
                )
                if args.dry_run:
                    await session.rollback()
                else:
                    await session.commit()
            except Exception:
                await session.rollback()
                raise
    except SeedError as exc:
        print(f"Seed aborted: {exc}", file=sys.stderr)
        return 1
    finally:
        await async_engine.dispose()

    mode = "DRY RUN (rolled back)" if args.dry_run else "committed"
    print(
        f"Seed {mode}: account={report.account_id} customers={report.customers} "
        f"invoices={report.invoices} payments={report.payments} "
        f"member={report.member_email or '-'}"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed synthetic Orvian demo business data.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--anchor-date", type=date.fromisoformat, default=DEFAULT_ANCHOR)
    parser.add_argument("--member", help="Email of an existing verified user to grant access.")
    parser.add_argument("--dry-run", action="store_true", help="Generate and roll back.")
    args = parser.parse_args()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    raise SystemExit(asyncio.run(_main(args)))


if __name__ == "__main__":
    main()
