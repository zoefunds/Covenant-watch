from __future__ import annotations

import threading

import pytest

from app.workers import indexer


def test_sync_rejects_overlap_while_worker_is_in_flight(monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    def blocked_sync():
        entered.set()
        assert release.wait(timeout=2)

    monkeypatch.setattr(indexer, "_run_sync_once_unlocked", blocked_sync)
    worker = threading.Thread(target=indexer.run_sync_once)
    worker.start()
    assert entered.wait(timeout=1)

    with pytest.raises(indexer.SyncAlreadyRunningError):
        indexer.run_sync_once()

    release.set()
    worker.join(timeout=2)
    assert not worker.is_alive()


def test_sync_lock_is_released_after_failure(monkeypatch):
    calls = 0

    def failing_then_succeeding():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")

    monkeypatch.setattr(indexer, "_run_sync_once_unlocked", failing_then_succeeding)
    with pytest.raises(RuntimeError, match="boom"):
        indexer.run_sync_once()
    indexer.run_sync_once()
    assert calls == 2
