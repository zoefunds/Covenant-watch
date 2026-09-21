"""
Distributed, Redis-backed hourly budget tracker for outbound genlayer-py
RPC calls.

Why this exists: GenLayer's RPC has an account/endpoint-wide limit of
5000 requests/hour. This backend can run multiple Fly.io machines and also
runs a continuously-polling indexer worker, so an in-process counter is not
enough -- every machine needs to agree on how much of the hourly budget is
left. Redis (a single shared Upstash instance, see REDIS_URL) is the
coordination point.

This module is the SINGLE choke point for that budget check -- the
intended parallel (see repo-root memory.md) is `_send_gen` in
`contracts/covenant_watch.py`, which is the contract's own single funnel
for every fund movement. Just as no code path is allowed to move GEN
without going through `_send_gen`, no code path is allowed to make a
genlayer-py call without going through `check_and_increment_rpc_budget()`
(or the wrapped call helpers in `app/services/chain_client.py` that call
it). Grep for `check_and_increment_rpc_budget` to find every outbound RPC
call site in this codebase.

Design: fixed hourly window keyed by the wall-clock UTC hour
(`genlayer:rpc_budget:<epoch_hour>`), incremented atomically with `INCR`
(atomic on its own -- no two callers can ever read/increment the same
value) followed by `EXPIRE ... NX` (only sets the TTL the first time the
key is created, so concurrent callers racing to be "first" never reset
each other's window) -- two round trips, but both operations are
individually atomic server-side, so there is no lost-update window. Capped
at `GENLAYER_RPC_HOURLY_BUDGET` (default 4000, comfortably under
GenLayer's 5000/hour ceiling to leave headroom for retries/other tooling
hitting the same account). The key expires on its own ~2h after the
window starts, so no cleanup job is needed.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import redis

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)

_WINDOW_SECONDS = 3600

_redis_client: Optional["redis.Redis"] = None


def _client() -> "redis.Redis":
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


def _current_window() -> tuple[int, int]:
    """Returns (window_start_epoch_hour, seconds_until_reset)."""
    now = int(time.time())
    window_start = now - (now % _WINDOW_SECONDS)
    reset_in = _WINDOW_SECONDS - (now - window_start)
    return window_start, reset_in


def _bucket_key(window_start: int) -> str:
    return f"genlayer:rpc_budget:{window_start}"


class RpcBudgetExhaustedError(Exception):
    """Raised when the hourly GenLayer RPC budget has been used up for the
    current window. Carries `retry_after_seconds` so callers (the indexer's
    backoff loop, or a request-time 503 handler) know exactly how long to
    wait -- always <= 3600s since windows are fixed hourly buckets."""

    def __init__(self, used: int, limit: int, retry_after_seconds: int):
        self.used = used
        self.limit = limit
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"GenLayer RPC hourly budget exhausted ({used}/{limit} used this window); "
            f"retry in {retry_after_seconds}s"
        )


@dataclass
class RpcBudgetStatus:
    used: int
    limit: int
    remaining: int
    window_reset_seconds: int
    window_reset_at_epoch: int


def check_and_increment_rpc_budget(reason: str = "") -> None:
    """Call this immediately before every outbound genlayer-py RPC call.
    Raises RpcBudgetExhaustedError instead of letting the call through if
    the current hourly window is already at/over budget. On any Redis
    failure (network blip against the Upstash instance, etc.) this
    fails OPEN -- i.e. it logs loudly and allows the call -- because a
    coordination-layer outage should degrade to "no coordination" (the old
    behavior) rather than taking the whole app down; GenLayer's own RPC
    will still hard-reject if we truly exceed its limit.
    """
    settings = get_settings()
    limit = settings.GENLAYER_RPC_HOURLY_BUDGET
    window_start, reset_in = _current_window()
    key = _bucket_key(window_start)

    try:
        client = _client()
        count = client.incr(key)
        if count == 1:
            client.expire(key, _WINDOW_SECONDS * 2, nx=True)
    except Exception as e:  # noqa: BLE001 - fail open on Redis outage
        log.error(
            "rpc_budget.redis_unavailable_failing_open",
            error=str(e),
            reason=reason,
        )
        return

    if count > limit:
        log.warning(
            "rpc_budget.exhausted",
            used=count,
            limit=limit,
            reset_in_seconds=reset_in,
            reason=reason,
        )
        raise RpcBudgetExhaustedError(used=count, limit=limit, retry_after_seconds=reset_in)

    if count == limit or count == int(limit * 0.9):
        log.warning(
            "rpc_budget.approaching_limit",
            used=count,
            limit=limit,
            reset_in_seconds=reset_in,
            reason=reason,
        )


def get_rpc_budget_status() -> RpcBudgetStatus:
    """Read-only status for /healthz and /internal/rate-budget. Never
    increments. Returns a zeroed status (fails open, same policy as the
    increment path) if Redis is unreachable."""
    settings = get_settings()
    limit = settings.GENLAYER_RPC_HOURLY_BUDGET
    window_start, reset_in = _current_window()
    key = _bucket_key(window_start)

    try:
        raw = _client().get(key)
        used = int(raw) if raw is not None else 0
    except Exception as e:  # noqa: BLE001
        log.error("rpc_budget.status_redis_unavailable", error=str(e))
        used = 0

    return RpcBudgetStatus(
        used=used,
        limit=limit,
        remaining=max(0, limit - used),
        window_reset_seconds=reset_in,
        window_reset_at_epoch=window_start + _WINDOW_SECONDS,
    )
