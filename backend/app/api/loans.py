from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session as DBSession

from app.database import get_db
from app.models.check import Check
from app.models.covenant import Covenant
from app.models.loan import Loan
from app.schemas.domain import CheckOut, CovenantOut, LoanOut

router = APIRouter(prefix="/loans", tags=["loans"])


@router.get("", response_model=list[LoanOut])
def list_loans(
    address: str | None = Query(default=None, description="filter: lender or borrower address"),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: DBSession = Depends(get_db),
):
    q = db.query(Loan)
    if address:
        addr = address.lower()
        q = q.filter((Loan.lender_address == addr) | (Loan.borrower_address == addr))
    if status_filter:
        q = q.filter(Loan.status == status_filter)
    return q.order_by(Loan.chain_loan_id.desc()).offset(offset).limit(limit).all()


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
