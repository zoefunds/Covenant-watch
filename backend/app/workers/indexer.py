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
import threading
import time
from typing import Any

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from sqlalchemy import text

from app.core.config import get_settings
from app.core.logging import get_logger
from app.database import session_scope
from app.models.check import Check, CheckStatus
from app.models.challenge import Challenge
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
_SYNC_LOCK = threading.Lock()


class SyncAlreadyRunningError(Exception):
    """A sync is already in flight in this process.

    Crucially, a timed-out asyncio waiter does not cancel its worker thread;
    this lock remains held by that thread until the real RPC call exits, so a
    timeout can never create an accumulating pile of replacement threads.
    """


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
    row.lender_address = str(loan_dict.get("lender", "")).lower()
    row.borrower_address = str(loan_dict.get("borrower", "")).lower()
    row.principal_wei = str(loan_dict.get("principal_wei", 0))
    row.collateral_wei = str(loan_dict.get("collateral_wei", 0))
    # Contract's _loan_dict emits base_interest_bps (fixed at creation) and
    # current_interest_bps (can step up on a tier1 breach) -- there is no
    # plain "interest_bps" key. The cached column tracks the LIVE rate, so
    # prefer current_interest_bps and fall back to base_interest_bps for
    # any older snapshot that only has the base rate.
    row.interest_bps = int(loan_dict.get("current_interest_bps", loan_dict.get("base_interest_bps", 0)))
    row.maturity_ts = int(loan_dict.get("maturity_ts", 0))
    row.status = str(loan_dict.get("status", "unknown"))
    row.principal_deposited = str(loan_dict.get("principal_deposited", 0))
    row.principal_claimed = bool(loan_dict.get("principal_claimed", False))
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
    source_type = str(cov_dict.get("source_type", "offchain")).lower()
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
    # No "validator_result" key on the real check dict -- the closest
    # equivalent is the observed value/note/source-hash the contract
    # actually emits from evaluation.
    row.validator_result = {
        "observed_value": check_dict.get("observed_value"),
        "observed_note": check_dict.get("observed_note"),
        "result_source_hash": check_dict.get("result_source_hash"),
    }
    status = str(check_dict.get("status", "pending")).lower()
    try:
        row.status = CheckStatus(status)
    except ValueError:
        row.status = CheckStatus.pending
    triggered_ts = check_dict.get("triggered_at") or check_dict.get("snapshot_ts") or 0
    row.triggered_at = dt.datetime.fromtimestamp(int(triggered_ts), tz=dt.timezone.utc) if triggered_ts else dt.datetime.now(dt.timezone.utc)
    # No "finalized_at" timestamp on the real check dict -- it has a plain
    # "finalized" boolean instead. evaluated_at is the closest real
    # timestamp for when that finalization-eligible state was reached.
    finalized_ts = check_dict.get("evaluated_at") if check_dict.get("finalized") else None
    row.finalized_at = (
        dt.datetime.fromtimestamp(int(finalized_ts), tz=dt.timezone.utc) if finalized_ts else None
    )
    row.raw_snapshot = check_dict
    db.add(row)
    db.flush()
    return row


def _sync_loan(db, client, address: str, chain_loan_id: int) -> None:
    """Synchronize one loan and its dependent cache rows.

    Kept intentionally small so the main pass can discover every new loan
    while only refreshing a bounded active working set on later passes.
    """
    try:
        loan_dict = _call_view(client, address, "get_loan", [chain_loan_id])
    except Exception as exc:  # noqa: BLE001
        log.error("indexer.loan_read_failed", loan_id=chain_loan_id, error=str(exc))
        raise
    if not loan_dict:
        return
    loan_row = _upsert_loan(db, chain_loan_id, loan_dict)
    covenants = _call_view(client, address, "get_loan_covenants", [chain_loan_id]) or []
    for cov_dict in covenants:
        if not cov_dict:
            continue
        chain_covenant_id = cov_dict.get("id")
        if chain_covenant_id is None:
            continue
        cov_row = _upsert_covenant(db, loan_row, int(chain_covenant_id), cov_dict)
        try:
            checks = _call_view(client, address, "get_covenant_check_history", [chain_covenant_id]) or []
        except Exception as exc:  # noqa: BLE001
            log.warning("indexer.check_history_read_failed", covenant_id=chain_covenant_id, error=str(exc))
            checks = []
        for check_dict in checks:
            chain_check_id = check_dict.get("id")
            if chain_check_id is not None:
                _upsert_check(db, cov_row, int(chain_check_id), check_dict)


def _run_sync_once_unlocked() -> None:
    """Discover all new loans and refresh a bounded set of live loans.

    This keeps the backend as the sole regular RPC poller without letting a
    growing historic portfolio consume the whole GenLayer hourly budget.
    """
    settings = get_settings()
    client = get_client()
    address = settings.CONTRACT_ADDRESS

    with session_scope() as db:
        # Transaction-scoped advisory lock is the cross-process/cross-replica
        # lease. Unlike locking the cursor row, it is race-free even on the
        # very first pass before that row exists. The DB releases it only when
        # this transaction ends, including if the asyncio waiter has timed out
        # while its worker thread remains stuck in a synchronous RPC call.
        lease_acquired = db.execute(
            text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
            {"lock_id": 0x434F56454E414E54},  # "COVENANT" as a stable 64-bit key
        ).scalar()
        if not lease_acquired:
            raise SyncAlreadyRunningError("another backend replica is already syncing")

        cursor = db.get(SyncCursor, "default")
        if cursor is None:
            cursor = SyncCursor(shard_key="default", last_synced_loan_id=0)
            db.add(cursor)
            db.flush()

        configured_address = str(address).lower()
        if cursor.contract_address != configured_address:
            # Contract IDs restart at zero on every deployment. Keeping old
            # rows would silently serve a different contract's loan as the
            # new deployment's loan #0, which is unsafe even for read views.
            db.query(Challenge).delete(synchronize_session=False)
            db.query(Check).delete(synchronize_session=False)
            db.query(Covenant).delete(synchronize_session=False)
            db.query(Loan).delete(synchronize_session=False)
            cursor.last_synced_loan_id = 0
            log.warning("indexer.cache_reset_for_contract_change", previous=cursor.contract_address, current=configured_address)
        cursor.contract_address = configured_address

        try:
            loan_count = _call_view(client, address, "get_loan_count")
        except Exception as exc:  # noqa: BLE001 - attribute the failing call before it bubbles up
            log.error("indexer.loan_count_read_failed", error=str(exc))
            raise
        loan_count = int(loan_count)

        new_ids = range(int(cursor.last_synced_loan_id), loan_count)
        synced_ids: set[int] = set()
        for chain_loan_id in new_ids:
            _sync_loan(db, client, address, chain_loan_id)
            synced_ids.add(chain_loan_id)
        cursor.last_synced_loan_id = loan_count

        live_statuses = ("CREATED", "ACTIVE", "BREACH_TIER1", "BREACH_TIER2")
        refresh_ids = [
            row.chain_loan_id
            for row in db.query(Loan)
            .filter(Loan.status.in_(live_statuses))
            .order_by(Loan.updated_at.asc())
            .limit(settings.INDEXER_MAX_REFRESH_LOANS)
            .all()
        ]
        for chain_loan_id in refresh_ids:
            if chain_loan_id not in synced_ids:
                _sync_loan(db, client, address, chain_loan_id)

        cursor.last_run_at = dt.datetime.now(dt.timezone.utc)
        cursor.last_success_at = dt.datetime.now(dt.timezone.utc)
        cursor.last_error = None
        db.add(cursor)


def run_sync_once() -> None:
    """Run one serialized sync pass, rejecting concurrent callers."""
    if not _SYNC_LOCK.acquire(blocking=False):
        raise SyncAlreadyRunningError("an indexer sync pass is already running")
    try:
        _run_sync_once_unlocked()
    finally:
        _SYNC_LOCK.release()


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
            # run_sync_once() is synchronous (genlayer-py's HTTP client has
            # no configurable request timeout), so it runs in a worker
            # thread rather than directly on this coroutine -- a single
            # stuck RPC call used to be able to freeze indexing forever
            # with no error ever logged, since nothing here would time it
            # out. wait_for() forces a hard ceiling for this coroutine. Python
            # cannot kill the underlying worker thread, so run_sync_once's
            # process-wide lock remains held until that thread truly exits;
            # later cycles are rejected instead of spawning more stuck work.
            # The timeout is generous (3x the normal
            # poll interval, minimum 5 minutes) since a full pass walking
            # every loan/covenant/check is legitimately slower than a
            # single RPC call.
            await asyncio.wait_for(
                asyncio.to_thread(run_sync_once),
                timeout=max(300, settings.INDEXER_POLL_INTERVAL_SECONDS * 3),
            )
            _STATUS["last_success_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            _STATUS["last_error"] = None
            _STATUS["state"] = "idle"
        except asyncio.TimeoutError:
            _STATUS["state"] = "error"
            _STATUS["last_error"] = "sync pass timed out; its worker remains isolated until the RPC call exits"
            log.error("indexer.sync_timed_out")
        except SyncAlreadyRunningError as e:
            _STATUS["state"] = "waiting_for_inflight_sync"
            _STATUS["last_error"] = str(e)
            log.warning("indexer.sync_already_running")
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
