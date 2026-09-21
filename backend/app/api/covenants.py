from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.database import get_db
from app.models.challenge import Challenge
from app.models.check import Check
from app.models.covenant import Covenant
from app.schemas.domain import ChallengeOut, CheckOut, CovenantOut, PreviewSourceRequest, PreviewSourceResponse
from app.services.url_preview import SSRFBlockedError, fetch_preview

router = APIRouter(prefix="/covenants", tags=["covenants"])
settings = get_settings()
# Same Redis-backed storage_uri as app.main.limiter -- shares the backing
# store so per-address limits stay consistent across instances (slowapi
# limiter instances are per-module here, but they must agree on storage).
limiter = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)


@router.get("/{covenant_id}", response_model=CovenantOut)
def get_covenant(covenant_id: int, db: DBSession = Depends(get_db)):
    row = db.query(Covenant).filter(Covenant.chain_covenant_id == covenant_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="covenant not found in cache")
    return row


@router.get("/{covenant_id}/checks", response_model=list[CheckOut])
def get_covenant_checks(covenant_id: int, db: DBSession = Depends(get_db)):
    cov_row = db.query(Covenant).filter(Covenant.chain_covenant_id == covenant_id).one_or_none()
    if cov_row is None:
        raise HTTPException(status_code=404, detail="covenant not found in cache")
    return db.query(Check).filter(Check.covenant_id == cov_row.id).order_by(Check.triggered_at.desc()).all()


@router.get("/checks/{check_id}/challenges", response_model=list[ChallengeOut])
def get_check_challenges(check_id: int, db: DBSession = Depends(get_db)):
    check_row = db.query(Check).filter(Check.chain_check_id == check_id).one_or_none()
    if check_row is None:
        raise HTTPException(status_code=404, detail="check not found in cache")
    return db.query(Challenge).filter(Challenge.check_id == check_row.id).order_by(Challenge.submitted_at).all()


@router.post("/preview-source", response_model=PreviewSourceResponse)
@limiter.limit(settings.RATE_LIMIT_WRITE_ADJACENT)
async def preview_source(request: Request, payload: PreviewSourceRequest):
    """SSRF-protected preview of an offchain covenant source URL, shown to
    the loan creator before pinning it. Informational only -- the contract
    performs its own independent fetch at check time; nothing here feeds
    consensus."""
    try:
        result = await fetch_preview(payload.url)
    except SSRFBlockedError as e:
        raise HTTPException(status_code=400, detail=f"URL rejected: {e}") from e
    import datetime as dt

    return PreviewSourceResponse(
        url=result["url"],
        status_code=result["status_code"],
        content_type=result["content_type"],
        truncated_body=result["truncated_body"],
        fetched_at=dt.datetime.now(dt.timezone.utc).isoformat(),
    )
