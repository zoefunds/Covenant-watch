from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session as DBSession

from app.api.deps import require_session
from app.core.config import get_settings
from app.core.logging import get_logger
from app.database import get_db
from app.models.session import Session as SessionModel
from app.schemas.auth import NonceRequest, NonceResponse, SessionInfo, VerifyRequest
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)
settings = get_settings()
# Same Redis-backed storage_uri as app.main.limiter/app.api.covenants.limiter
# so per-address limits are consistent across Fly.io machines.
limiter = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)


@router.post("/nonce", response_model=NonceResponse)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def issue_nonce(request: Request, payload: NonceRequest, db: DBSession = Depends(get_db)):
    nonce_row = auth_service.issue_nonce(db, payload.address)
    message = auth_service.build_siwe_message(payload.address, nonce_row.nonce, nonce_row.expires_at)
    return NonceResponse(
        address=payload.address,
        nonce=nonce_row.nonce,
        message=message,
        expires_at=nonce_row.expires_at.isoformat(),
    )


@router.post("/verify", response_model=SessionInfo)
@limiter.limit(settings.RATE_LIMIT_AUTH)
def verify(request: Request, payload: VerifyRequest, response: Response, db: DBSession = Depends(get_db)):
    try:
        auth_service.verify_and_consume_nonce(db, payload.address, payload.message, payload.signature)
    except auth_service.AuthError as e:
        log.warning("auth.verify_failed", address=payload.address, error=str(e))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e

    token, expires_at = auth_service.create_session(db, payload.address)

    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",
        domain=settings.COOKIE_DOMAIN,
        max_age=settings.SESSION_TTL_SECONDS,
        path="/",
    )
    return SessionInfo(address=payload.address, expires_at=expires_at.isoformat())


@router.post("/logout")
def logout(response: Response, db: DBSession = Depends(get_db), session_row: SessionModel = Depends(require_session)):
    auth_service.revoke_session(db, session_row)
    response.delete_cookie(key=settings.SESSION_COOKIE_NAME, path="/")
    return {"status": "logged_out"}


@router.get("/me", response_model=SessionInfo)
def me(session_row: SessionModel = Depends(require_session)):
    return SessionInfo(address=session_row.address, expires_at=session_row.expires_at.isoformat())
