from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Session(Base):
    """Server-side record of an issued session, keyed by session id (jti).
    The cookie carries a signed token referencing this row's id; revocation
    (logout) just deletes/expires the row so a stolen cookie alone isn't
    enough once revoked."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # random session id (jti)
    address: Mapped[str] = mapped_column(String(42), nullable=False, index=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
