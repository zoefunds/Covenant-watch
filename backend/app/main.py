from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import auth, covenants, health, loans
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.sentry import init_sentry
from app.services.rpc_budget import RpcBudgetExhaustedError
from app.workers.indexer import indexer_loop

configure_logging()
init_sentry()
log = get_logger(__name__)
settings = get_settings()

# Redis-backed storage so per-address/per-endpoint slowapi limits are
# consistent across multiple Fly.io machines (was in-process-only before,
# which meant each machine had its own independent counter). Same Redis
# instance used for the GenLayer RPC hourly budget (app/services/rpc_budget.py).
limiter = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)

_stop_event: asyncio.Event | None = None
_indexer_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _stop_event, _indexer_task
    _stop_event = asyncio.Event()
    _indexer_task = asyncio.create_task(indexer_loop(_stop_event))
    log.info("app.startup", contract_configured=bool(settings.CONTRACT_ADDRESS))
    yield
    _stop_event.set()
    if _indexer_task:
        await asyncio.wait_for(_indexer_task, timeout=10)
    log.info("app.shutdown")


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RpcBudgetExhaustedError)
async def rpc_budget_exhausted_handler(request: Request, exc: RpcBudgetExhaustedError):
    """Any request-time code path that reads live from the chain (e.g.
    `app.services.chain_client.read_contract_view`) and hits an exhausted
    hourly GenLayer RPC budget lands here instead of falling through to the
    generic 500 handler -- a typed 503 with Retry-After, not a hang or an
    opaque error."""
    log.warning(
        "rpc_budget.request_rejected",
        path=str(request.url),
        used=exc.used,
        limit=exc.limit,
        retry_after=exc.retry_after_seconds,
    )
    return JSONResponse(
        status_code=503,
        headers={"Retry-After": str(exc.retry_after_seconds)},
        content={
            "detail": "GenLayer RPC hourly budget exhausted; try again after the window resets.",
            "retry_after_seconds": exc.retry_after_seconds,
            "used": exc.used,
            "limit": exc.limit,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("unhandled_exception", path=str(request.url))
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(loans.router)
app.include_router(covenants.router)


@app.get("/")
def root():
    return {"service": settings.APP_NAME, "status": "ok"}
