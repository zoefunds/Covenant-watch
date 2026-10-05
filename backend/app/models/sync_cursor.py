from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SyncCursor(Base):
    """Per-shard indexer progress marker. shard_key is 'default' unless we
    ever split indexing by loan-id-range; the indexer worker can be safely
    restarted and will resume from last_synced_loan_id -- the cache can
    always be rebuilt from genesis by resetting this row."""

    __tablename__ = "sync_cursor"

    shard_key: Mapped[str] = mapped_column(String(64), primary_key=True, default="default")
    last_synced_loan_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # The cache has no economic meaning and must never mix IDs from two
    # deployments, because every fresh contract starts loan IDs at zero.
    contract_address: Mapped[str | None] = mapped_column(String(42), nullable=True)
    last_synced_block: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    last_run_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
