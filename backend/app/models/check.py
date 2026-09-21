from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CheckStatus(str, enum.Enum):
    pending = "pending"
    compliant = "compliant"
    breach = "breach"
    inconclusive = "inconclusive"


class Check(Base):
    __tablename__ = "checks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chain_check_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    covenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("covenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chain_covenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    chain_loan_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    triggered_by: Mapped[str] = mapped_column(String(42), nullable=False, index=True)

    pinned_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=False, comment="{hash, url_or_ref, block, timestamp}"
    )

    validator_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[CheckStatus] = mapped_column(Enum(CheckStatus, name="check_status_enum"), nullable=False, index=True)

    triggered_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finalized_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    raw_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_checks_covenant_status", "covenant_id", "status"),)
