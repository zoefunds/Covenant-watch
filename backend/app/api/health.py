from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.database import get_db
from app.schemas.domain import HealthOut
from app.services.rpc_budget import get_rpc_budget_status
from app.workers.indexer import get_indexer_status

router = APIRouter(tags=["health"])
settings = get_settings()


def _rpc_budget_dict() -> dict:
    status = get_rpc_budget_status()
    return {
        "used": status.used,
        "limit": status.limit,
        "remaining": status.remaining,
        "window_reset_seconds": status.window_reset_seconds,
        "window_reset_at_epoch": status.window_reset_at_epoch,
    }


@router.get("/healthz", response_model=HealthOut)
def healthz(db: DBSession = Depends(get_db)):
    db_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001
        db_status = f"error: {e}"

    return HealthOut(
        status="ok" if db_status == "ok" else "degraded",
        database=db_status,
        indexer=get_indexer_status(),
        contract_configured=bool(settings.CONTRACT_ADDRESS),
        rpc_budget=_rpc_budget_dict(),
    )


@router.get("/internal/rate-budget")
def rate_budget():
    """Observability endpoint: current GenLayer RPC hourly budget usage,
    shared across all backend instances via Redis (app/services/rpc_budget.py).
    Also duplicated inside /healthz's `rpc_budget` field for convenience."""
    return _rpc_budget_dict()
