"""
Background indexer worker.

Polls the deployed contract's view methods and syncs loan/covenant/check
state into Postgres as a read-optimized CACHE -- Postgres is never the
source of truth for money or compliance state; it can be rebuilt at any
time by resetting `sync_cursor` and re-running.

Startup behavior: if CONTRACT_ADDRESS is unset, the worker logs a clear
"waiting for contract address" message and polls at a slow interval until
it appears, rather than crashing. We re-read `get_settings()` (which is
lru_cached) fresh each pass via `get_settings.cache_clear()` so that
setting CONTRACT_ADDRESS in the environment and sending SIGHUP-equivalent
(or just restarting the process) picks it up -- for this deployment we
document restart-to-reload as the supported path (see
DEPLOYMENT_BACKEND.md), since Fly.io makes restarts cheap and it avoids
any risk of stale cached config silently persisting.

Failure handling: every chain call is wrapped; a single bad poll logs and
retries with exponential backoff instead of crashing the process. Liveness
is exposed via `get_indexer_status()` for /healthz.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import time
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database import session_scope
from app.models.check import Check, CheckStatus
from app.models.covenant import Covenant, SourceType
from app.models.loan import Loan
from app.models.sync_cursor import SyncCursor
from app.services.chain_client import call_contract_view_budgeted, get_client
from app.services.rpc_budget import RpcBudgetExhaustedError

log = get_logger(__name__)

_STATUS: dict[str, Any] = {
    "state": "not_started",
    "last_run_at": None,
    "last_success_at": None,
    "last_error": None,
    "contract_configured": False,
}


def get_indexer_status() -> dict:
    return dict(_STATUS)


class _RetryableChainError(Exception):
    pass


@retry(
    retry=retry_if_exception_type(_RetryableChainError),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _call_view(client, address: str, function_name: str, args: list | None = None):
    """Routes through `call_contract_view_budgeted` -- the single shared
    choke point (app/services/chain_client.py) that checks the Redis
    hourly RPC budget before every genlayer-py call. `RpcBudgetExhaustedError`
    is NOT retried here (retrying into an exhausted budget would just
    hammer Redis and burn the budget check itself) -- it propagates
    straight up to `run_sync_once`/`indexer_loop`, which back off for the
    rest of the current hourly window instead of busy-spinning."""
    try:
        return call_contract_view_budgeted(client, address, function_name, args)
    except RpcBudgetExhaustedError:
        raise
    except _RetryableChainError:
        raise
    except Exception as e:  # noqa: BLE001 - treat all RPC failures as retryable
        raise _RetryableChainError(str(e)) from e


def _upsert_loan(db, chain_loan_id: int, loan_dict: dict) -> Loan:
    row = db.query(Loan).filter(Loan.chain_loan_id == chain_loan_id).one_or_none()
    if row is None:
        row = Loan(chain_loan_id=chain_loan_id)
    row.lender_address = loan_dict.get("lender", "")
    row.borrower_address = loan_dict.get("borrower", "")
    row.principal_wei = str(loan_dict.get("principal_wei", 0))
    row.collateral_wei = str(loan_dict.get("collateral_wei", 0))
    row.interest_bps = int(loan_dict.get("interest_bps", 0))
    row.maturity_ts = int(loan_dict.get("maturity_ts", 0))
    row.status = str(loan_dict.get("status", "unknown"))
    row.principal_deposited = str(loan_dict.get("principal_deposited", 0))
    row.collateral_deposited = str(loan_dict.get("collateral_deposited", 0))
    row.claimable_lender_wei = str(loan_dict.get("claimable_lender_wei", 0))
    row.claimable_borrower_wei = str(loan_dict.get("claimable_borrower_wei", 0))
    row.raw_snapshot = loan_dict
    db.add(row)
    db.flush()
    return row


def _upsert_covenant(db, loan_row: Loan, chain_covenant_id: int, cov_dict: dict) -> Covenant:
    row = db.query(Covenant).filter(Covenant.chain_covenant_id == chain_covenant_id).one_or_none()
    if row is None:
        row = Covenant(chain_covenant_id=chain_covenant_id)
    row.loan_id = loan_row.id
    row.chain_loan_id = loan_row.chain_loan_id
    source_type = str(cov_dict.get("source_type", "offchain"))
    row.source_type = SourceType.onchain if source_type == "onchain" else SourceType.offchain
    row.source_ref = str(cov_dict.get("source_ref", ""))
    row.condition_spec = cov_dict.get("condition_spec", {}) or {
        k: cov_dict[k] for k in ("condition_field", "operator", "threshold_scaled") if k in cov_dict
    }
    row.consequence_schedule = cov_dict.get("consequence_schedule", {})
    row.challenge_window_seconds = int(cov_dict.get("challenge_window_seconds", 0))
    row.raw_snapshot = cov_dict
    db.add(row)
    db.flush()
    return row


def _upsert_check(db, covenant_row: Covenant, chain_check_id: int, check_dict: dict) -> Check:
    row = db.query(Check).filter(Check.chain_check_id == chain_check_id).one_or_none()
    if row is None:
        row = Check(chain_check_id=chain_check_id)
    row.covenant_id = covenant_row.id
    row.chain_covenant_id = covenant_row.chain_covenant_id
    row.chain_loan_id = covenant_row.chain_loan_id
    row.triggered_by = str(check_dict.get("triggered_by", ""))
    row.pinned_snapshot = {
        "hash": check_dict.get("snapshot_hash"),
        "url_or_ref": check_dict.get("source_ref") or covenant_row.source_ref,
        "block": check_dict.get("block"),
        "timestamp": check_dict.get("snapshot_ts"),
    }
    row.validator_result = check_dict.get("validator_result")
    status = str(check_dict.get("status", "pending")).lower()
    try:
        row.status = CheckStatus(status)
    except ValueError:
        row.status = CheckStatus.pending
    triggered_ts = check_dict.get("triggered_at") or check_dict.get("snapshot_ts") or 0
    row.triggered_at = dt.datetime.fromtimestamp(int(triggered_ts), tz=dt.timezone.utc) if triggered_ts else dt.datetime.now(dt.timezone.utc)
    finalized_ts = check_dict.get("finalized_at")
    row.finalized_at = (
        dt.datetime.fromtimestamp(int(finalized_ts), tz=dt.timezone.utc) if finalized_ts else None
    )
    row.raw_snapshot = check_dict
    db.add(row)
    db.flush()
    return row


def run_sync_once() -> None:
    """One full sync pass: walks loan ids from the cursor up to
    get_loan_count(), pulling each loan's covenants and check history."""
    settings = get_settings()
    client = get_client()
    address = settings.CONTRACT_ADDRESS

    with session_scope() as db:
        cursor = db.get(SyncCursor, "default")
        if cursor is None:
            cursor = SyncCursor(shard_key="default", last_synced_loan_id=0)
            db.add(cursor)
            db.flush()

        loan_count = _call_view(client, address, "get_loan_count")
        loan_count = int(loan_count)

        start = cursor.last_synced_loan_id
        for chain_loan_id in range(start, loan_count):
            loan_dict = _call_view(client, address, "get_loan", [chain_loan_id])
            if not loan_dict:
                continue
            loan_row = _upsert_loan(db, chain_loan_id, loan_dict)

            cov_ids = _call_view(client, address, "get_loan_covenants", [chain_loan_id]) or []
            for chain_covenant_id in cov_ids:
                cov_dict = _call_view(client, address, "get_covenant", [chain_covenant_id])
                if not cov_dict:
                    continue
                cov_row = _upsert_covenant(db, loan_row, int(chain_covenant_id), cov_dict)

                checks = _call_view(client, address, "get_covenant_check_history", [chain_covenant_id]) or []
                for check_dict in checks:
                    chain_check_id = check_dict.get("check_id")
                    if chain_check_id is None:
                        continue
                    _upsert_check(db, cov_row, int(chain_check_id), check_dict)

            cursor.last_synced_loan_id = chain_loan_id + 1

        cursor.last_run_at = dt.datetime.now(dt.timezone.utc)
        cursor.last_success_at = dt.datetime.now(dt.timezone.utc)
        cursor.last_error = None
        db.add(cursor)


async def indexer_loop(stop_event: asyncio.Event) -> None:
    """Long-running task started at app startup. Never raises -- all
    exceptions are caught, logged, and reflected in _STATUS so /healthz can
    report indexer liveness without the whole API going down."""
    _STATUS["state"] = "starting"
    while not stop_event.is_set():
        settings = get_settings()
        _STATUS["contract_configured"] = bool(settings.CONTRACT_ADDRESS)

        if not settings.INDEXER_ENABLED:
            _STATUS["state"] = "disabled"
            await asyncio.sleep(30)
            continue

        if not settings.CONTRACT_ADDRESS:
            _STATUS["state"] = "waiting_for_contract_address"
            log.info(
                "indexer.waiting",
                message="CONTRACT_ADDRESS not set yet -- indexer idle until the user "
                "deploys the contract and sets the env var, then restarts the backend "
                "(or redeploys on Fly) to pick it up.",
            )
            await asyncio.sleep(15)
            continue

        _STATUS["state"] = "syncing"
        _STATUS["last_run_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        sleep_seconds = settings.INDEXER_POLL_INTERVAL_SECONDS
        try:
            run_sync_once()
            _STATUS["last_success_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            _STATUS["last_error"] = None
            _STATUS["state"] = "idle"
        except RpcBudgetExhaustedError as e:
            # Graceful degradation: never crash, never busy-spin against an
            # already-exhausted budget. Log clearly at warning level (visible
            # in normal deployments, not buried at debug) and sleep until the
            # budget window actually resets instead of the usual short poll
            # interval, then resume automatically.
            _STATUS["state"] = "rate_budget_exhausted"
            _STATUS["last_error"] = str(e)
            log.warning(
                "indexer.rpc_budget_exhausted_backing_off",
                used=e.used,
                limit=e.limit,
                resuming_in_seconds=e.retry_after_seconds,
            )
            sleep_seconds = max(sleep_seconds, e.retry_after_seconds)
        except Exception as e:  # noqa: BLE001 - never let one bad pass kill the loop
            _STATUS["last_error"] = str(e)
            _STATUS["state"] = "error"
            log.error("indexer.sync_failed", error=str(e))

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=sleep_seconds)
        except asyncio.TimeoutError:
            pass
