from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    check_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("checks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chain_check_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    submitted_by: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    evidence_ref: Mapped[str] = mapped_column(String(2048), nullable=False)

    submitted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    raw_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
