from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Nonce(Base):
    """Single-use, short-TTL SIWE-style nonces. Stored in Postgres (not
    in-memory) so a backend restart never invalidates a nonce a wallet is
    mid-way through signing, and so multiple backend replicas share state."""

    __tablename__ = "nonces"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)
    nonce: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_nonces_address_used", "address", "used_at"),)
