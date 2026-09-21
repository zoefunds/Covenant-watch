from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.database import get_db
from app.schemas.domain import HealthOut
from app.workers.indexer import get_indexer_status

router = APIRouter(tags=["health"])
settings = get_settings()


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
    )
