"""
Unit tests for the Redis-backed GenLayer RPC hourly budget tracker
(app/services/rpc_budget.py). These use `fakeredis` -- an in-memory Redis
stand-in -- so the suite never has to reach the real Upstash instance on
every run. The real Upstash instance was separately, manually verified
during development (TLS connect, direct redis-cli key inspection against
a live genlayer-py call to the deployed contract) -- see backend/README.md
and repo-root memory.md for that record; that verification is not repeated
here since it requires live network + a deployed contract.
"""
from __future__ import annotations

import fakeredis
import pytest

from app.services import rpc_budget as rb


@pytest.fixture(autouse=True)
def _fake_redis(monkeypatch):
    """Point the module's singleton client at a fresh in-memory fakeredis
    instance for every test, and reset module-level caches so tests don't
    leak state into each other."""
    fake = fakeredis.FakeStrictRedis(decode_responses=True)
    monkeypatch.setattr(rb, "_redis_client", fake)
    monkeypatch.setattr(rb, "_client", lambda: fake)

    # get_settings() is lru_cached; patch the budget limit directly via
    # monkeypatching get_settings to avoid needing a real .env for these
    # pure-unit tests.
    class _FakeSettings:
        GENLAYER_RPC_HOURLY_BUDGET = 5

    monkeypatch.setattr(rb, "get_settings", lambda: _FakeSettings())
    yield fake


def test_increments_on_each_call():
    rb.check_and_increment_rpc_budget(reason="get_loan_count")
    rb.check_and_increment_rpc_budget(reason="get_loan_count")
    status = rb.get_rpc_budget_status()
    assert status.used == 2
    assert status.limit == 5
    assert status.remaining == 3


def test_raises_when_budget_exhausted():
    for _ in range(5):
        rb.check_and_increment_rpc_budget(reason="poll")

    with pytest.raises(rb.RpcBudgetExhaustedError) as exc_info:
        rb.check_and_increment_rpc_budget(reason="poll")

    err = exc_info.value
    assert err.used == 6
    assert err.limit == 5
    assert 0 < err.retry_after_seconds <= 3600

    status = rb.get_rpc_budget_status()
    assert status.remaining == 0


def test_status_is_read_only_and_does_not_increment():
    rb.check_and_increment_rpc_budget(reason="a")
    before = rb.get_rpc_budget_status()
    after = rb.get_rpc_budget_status()
    assert before.used == after.used == 1


def test_fails_open_when_redis_unavailable(monkeypatch):
    """Graceful degradation policy: a Redis-layer outage must not take
    the whole app down -- the check should fail open (allow the call,
    log loudly) rather than raise."""

    def _boom():
        raise ConnectionError("simulated redis outage")

    monkeypatch.setattr(rb, "_client", _boom)
    # Should not raise despite the simulated outage.
    rb.check_and_increment_rpc_budget(reason="during outage")


def test_indexer_backoff_path_surfaces_typed_error(monkeypatch):
    """Simulates a near-exhausted budget and confirms the indexer's
    graceful-degradation path (RpcBudgetExhaustedError -> backoff, never a
    crash) actually triggers, by driving the real
    app.workers.indexer._call_view wrapper against a stubbed chain client."""
    from app.workers.indexer import _call_view

    class _StubClient:
        def read_contract(self, address, function_name, args=None):
            return 42

    for _ in range(5):
        rb.check_and_increment_rpc_budget(reason="fill")

    with pytest.raises(rb.RpcBudgetExhaustedError):
        _call_view(_StubClient(), "0xdead", "get_loan_count")
