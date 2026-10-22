"""Tests for synthetic business data seed script: determinism, idempotency, and access scoping."""

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Customer, Invoice, Payment, User
from scripts.seed_business_data import (
    DEFAULT_ANCHOR,
    DEFAULT_SEED,
    SeedError,
    generate_dataset,
    seed_demo_data,
)
from tests.factories import create_user_with_session


def test_generate_dataset_determinism() -> None:
    test_account_id = uuid.uuid4()
    c1, i1, p1 = generate_dataset(DEFAULT_SEED, DEFAULT_ANCHOR, test_account_id)
    c2, i2, p2 = generate_dataset(DEFAULT_SEED, DEFAULT_ANCHOR, test_account_id)

    assert len(c1) == len(c2) == 40
    assert len(i1) == len(i2)
    assert len(p1) == len(p2)
    assert [c["external_ref"] for c in c1] == [c["external_ref"] for c in c2]
    assert [inv["invoice_number"] for inv in i1] == [inv["invoice_number"] for inv in i2]
    assert [p["amount_cents"] for p in p1] == [p["amount_cents"] for p in p2]


@pytest.mark.asyncio
async def test_seed_demo_data_idempotency(db_session: AsyncSession) -> None:
    # First seed execution
    r1 = await seed_demo_data(db_session, seed=DEFAULT_SEED, anchor=DEFAULT_ANCHOR)
    await db_session.commit()

    cust_count_1 = (await db_session.execute(select(func.count(Customer.id)))).scalar_one()
    inv_count_1 = (await db_session.execute(select(func.count(Invoice.id)))).scalar_one()
    pay_count_1 = (await db_session.execute(select(func.count(Payment.id)))).scalar_one()

    assert cust_count_1 == r1.customers == 40
    assert inv_count_1 == r1.invoices
    assert pay_count_1 == r1.payments

    # Second seed execution (same parameters)
    await seed_demo_data(db_session, seed=DEFAULT_SEED, anchor=DEFAULT_ANCHOR)
    await db_session.commit()

    cust_count_2 = (await db_session.execute(select(func.count(Customer.id)))).scalar_one()
    inv_count_2 = (await db_session.execute(select(func.count(Invoice.id)))).scalar_one()
    pay_count_2 = (await db_session.execute(select(func.count(Payment.id)))).scalar_one()

    # Counts must remain identical — no duplicate entries or constraint violations
    assert cust_count_1 == cust_count_2
    assert inv_count_1 == inv_count_2
    assert pay_count_1 == pay_count_2


@pytest.mark.asyncio
async def test_seed_demo_data_member_assignment(db_session: AsyncSession) -> None:
    # 1. Unverified user rejected
    user_unverified, _ = await create_user_with_session(
        db_session, "pending@example.com", verified=False
    )
    with pytest.raises(SeedError, match="must be verified and active"):
        await seed_demo_data(
            db_session,
            seed=DEFAULT_SEED,
            anchor=DEFAULT_ANCHOR,
            member_email="pending@example.com",
        )

    # 2. Non-existent user rejected
    with pytest.raises(SeedError, match="Member user not found"):
        await seed_demo_data(
            db_session,
            seed=DEFAULT_SEED,
            anchor=DEFAULT_ANCHOR,
            member_email="ghost@example.com",
        )

    # 3. Verified user successfully granted demo access
    user_verified, _ = await create_user_with_session(
        db_session, "verified@example.com", verified=True
    )
    assert user_verified.account_id is None

    report = await seed_demo_data(
        db_session,
        seed=DEFAULT_SEED,
        anchor=DEFAULT_ANCHOR,
        member_email="verified@example.com",
    )
    await db_session.commit()

    refreshed_user = (
        await db_session.execute(select(User).where(User.email == "verified@example.com"))
    ).scalar_one()

    assert refreshed_user.account_id == report.account_id
