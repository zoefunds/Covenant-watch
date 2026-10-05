from __future__ import annotations

import datetime as dt
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class LoanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chain_loan_id: int
    lender_address: str
    borrower_address: str
    principal_wei: str
    collateral_wei: str
    interest_bps: int
    maturity_ts: int
    status: str
    principal_deposited: str
    principal_claimed: bool
    collateral_deposited: str
    claimable_lender_wei: str
    claimable_borrower_wei: str
    updated_at: dt.datetime

    @field_validator(
        "principal_wei",
        "collateral_wei",
        "principal_deposited",
        "collateral_deposited",
        "claimable_lender_wei",
        "claimable_borrower_wei",
        mode="before",
    )
    @classmethod
    def coerce_numeric_strings(cls, value: Any) -> str:
        # PostgreSQL Numeric columns are returned as Decimal instances by
        # SQLAlchemy; the public API deliberately exposes exact integer
        # amounts as strings to avoid JSON precision loss in browsers.
        return str(value)


class CovenantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chain_covenant_id: int
    loan_id: int
    chain_loan_id: int
    source_type: str
    source_ref: str
    condition_spec: dict
    consequence_schedule: dict
    challenge_window_seconds: int
    updated_at: dt.datetime


class CheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    chain_check_id: int
    covenant_id: int
    chain_covenant_id: int
    chain_loan_id: int
    triggered_by: str
    pinned_snapshot: dict
    validator_result: Optional[dict]
    status: str
    triggered_at: dt.datetime
    finalized_at: Optional[dt.datetime]


class ChallengeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    check_id: int
    chain_check_id: int
    submitted_by: str
    evidence_ref: str
    submitted_at: dt.datetime
    resolved_at: Optional[dt.datetime]


class PreviewSourceRequest(BaseModel):
    url: str


class PreviewSourceResponse(BaseModel):
    url: str
    status_code: int
    content_type: Optional[str]
    truncated_body: str
    fetched_at: str
    note: str = (
        "Informational only. The contract performs its own independent fetch "
        "at check time; this preview never feeds consensus."
    )


class HealthOut(BaseModel):
    status: str
    database: str
    indexer: dict
    contract_configured: bool
    rpc_budget: dict
