from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, or_
from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.database import get_db
from app.models.check import Check
from app.models.covenant import Covenant
from app.models.loan import Loan
from app.schemas.domain import CheckOut, CovenantOut, LoanOut
from app.workers.indexer import SyncAlreadyRunningError, run_sync_once

router = APIRouter(prefix="/loans", tags=["loans"])
limiter = Limiter(key_func=get_remote_address, storage_uri=get_settings().REDIS_URL)


@router.get("", response_model=list[LoanOut])
def list_loans(
    address: str | None = Query(default=None, description="filter: lender or borrower address"),
    lender: str | None = Query(default=None, description="filter: lender address"),
    borrower: str | None = Query(default=None, description="filter: borrower address"),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: DBSession = Depends(get_db),
):
    q = db.query(Loan)
    if address:
        addr = address.lower()
        q = q.filter(or_(func.lower(Loan.lender_address) == addr, func.lower(Loan.borrower_address) == addr))
    if lender:
        q = q.filter(func.lower(Loan.lender_address) == lender.lower())
    if borrower:
        q = q.filter(func.lower(Loan.borrower_address) == borrower.lower())
    if status_filter:
        q = q.filter(Loan.status == status_filter)
    return q.order_by(Loan.chain_loan_id.desc()).offset(offset).limit(limit).all()


@router.post("/sync", response_model=list[LoanOut])
@limiter.limit("6/minute")
def sync_loans(request: Request, db: DBSession = Depends(get_db)):
    """One rate-limited cache refresh after a confirmed user write.

    The browser only asks the backend to sync; it never reads GenLayer RPC
    itself. Regular indexer polling remains the fallback.
    """
    try:
        run_sync_once()
    except SyncAlreadyRunningError as exc:
        raise HTTPException(status_code=409, detail="a cache refresh is already in progress") from exc
    return db.query(Loan).order_by(Loan.chain_loan_id.desc()).limit(200).all()


@router.get("/{loan_id}", response_model=LoanOut)
def get_loan(loan_id: int, db: DBSession = Depends(get_db)):
    row = db.query(Loan).filter(Loan.chain_loan_id == loan_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="loan not found in cache (not indexed yet, or does not exist)")
    return row


@router.get("/{loan_id}/covenants", response_model=list[CovenantOut])
def get_loan_covenants(loan_id: int, db: DBSession = Depends(get_db)):
    loan_row = db.query(Loan).filter(Loan.chain_loan_id == loan_id).one_or_none()
    if loan_row is None:
        raise HTTPException(status_code=404, detail="loan not found in cache")
    return db.query(Covenant).filter(Covenant.loan_id == loan_row.id).all()


@router.get("/{loan_id}/checks", response_model=list[CheckOut])
def get_loan_checks(loan_id: int, db: DBSession = Depends(get_db)):
    loan_row = db.query(Loan).filter(Loan.chain_loan_id == loan_id).one_or_none()
    if loan_row is None:
        raise HTTPException(status_code=404, detail="loan not found in cache")
    return (
        db.query(Check)
        .filter(Check.chain_loan_id == loan_id)
        .order_by(Check.triggered_at.desc())
        .all()
    )
