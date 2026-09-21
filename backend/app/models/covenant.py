from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SourceType(str, enum.Enum):
    onchain = "onchain"
    offchain = "offchain"


class Covenant(Base):
    """Cached covenant terms. Immutable on-chain post-creation (see contract
    docstrings) -- this cache mirrors that: we only ever INSERT/overwrite
    from a fresh chain read, never partially patch."""

    __tablename__ = "covenants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    chain_covenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    loan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("loans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chain_loan_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, name="source_type_enum"), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(2048), nullable=False)

    condition_spec: Mapped[dict] = mapped_column(JSONB, nullable=False)
    consequence_schedule: Mapped[dict] = mapped_column(JSONB, nullable=False)

    challenge_window_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False)

    raw_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_covenants_loan_source", "loan_id", "source_type"),)
