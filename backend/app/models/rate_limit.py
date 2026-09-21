from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RateLimitCounter(Base):
    """UX-only mirror of the contract's on-chain per-address-per-covenant
    cooldown, used solely to gray out a 'trigger check' button early on the
    frontend. This table is NEVER the enforcement point -- the contract's
    own cooldown (see get_cooldown_remaining) is authoritative and is
    re-checked server-side is not even required, since a stale button click
    just gets rejected on-chain. Kept here only as documented in memory.md.
    """

    __tablename__ = "rate_limit_counters"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    address: Mapped[str] = mapped_column(String(42), nullable=False)
    covenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    window_bucket: Mapped[int] = mapped_column(BigInteger, nullable=False)
    count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "ux_rate_limit_addr_cov_window",
            "address",
            "covenant_id",
            "window_bucket",
            unique=True,
        ),
    )
