from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Loan(Base):
    """
    Read-optimized CACHE of on-chain loan state, kept in sync by the indexer
    worker (app/workers/indexer.py). Postgres is NEVER the source of truth
    for money -- this table exists purely so the API can serve fast reads.
    Any balance-affecting decision the frontend makes MUST re-read the
    contract directly; see README "cache vs. live" section.
    """

    __tablename__ = "loans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chain_loan_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)

    lender_address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    borrower_address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)

    principal_wei: Mapped[str] = mapped_column(Numeric(78, 0), nullable=False)
    collateral_wei: Mapped[str] = mapped_column(Numeric(78, 0), nullable=False, default=0)
    interest_bps: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    maturity_ts: Mapped[int] = mapped_column(BigInteger, nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    principal_deposited: Mapped[str] = mapped_column(Numeric(78, 0), nullable=False, default=0)
    principal_claimed: Mapped[bool] = mapped_column(nullable=False, default=False)
    collateral_deposited: Mapped[str] = mapped_column(Numeric(78, 0), nullable=False, default=0)
    claimable_lender_wei: Mapped[str] = mapped_column(Numeric(78, 0), nullable=False, default=0)
    claimable_borrower_wei: Mapped[str] = mapped_column(Numeric(78, 0), nullable=False, default=0)

    create_tx_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_sync_tx_hash: Mapped[str | None] = mapped_column(String(80), nullable=True)

    raw_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        CheckConstraint("principal_wei >= 0", name="ck_loans_principal_nonneg"),
        CheckConstraint("collateral_wei >= 0", name="ck_loans_collateral_nonneg"),
        CheckConstraint("principal_deposited >= 0", name="ck_loans_principal_dep_nonneg"),
        CheckConstraint("collateral_deposited >= 0", name="ck_loans_collateral_dep_nonneg"),
        CheckConstraint("claimable_lender_wei >= 0", name="ck_loans_claimable_lender_nonneg"),
        CheckConstraint("claimable_borrower_wei >= 0", name="ck_loans_claimable_borrower_nonneg"),
        Index("ix_loans_lender_status", "lender_address", "status"),
        Index("ix_loans_borrower_status", "borrower_address", "status"),
    )
