from __future__ import annotations

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.database import get_db
from app.models.session import Session as SessionModel
from app.services.auth import resolve_session

settings = get_settings()


def require_session(
    db: DBSession = Depends(get_db),
    cw_session: str | None = Cookie(default=None, alias=settings.SESSION_COOKIE_NAME),
) -> SessionModel:
    """Every protected endpoint depends on this. A connected wallet address
    claimed in a request body/query is NEVER sufficient -- only a resolved,
    valid, unrevoked session cookie counts."""
    cookie_value = cw_session
    if not cookie_value:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    session_row = resolve_session(db, cookie_value)
    if session_row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired session")
    return session_row
