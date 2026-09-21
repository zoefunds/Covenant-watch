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
from app.workers.indexer import indexer_loop

configure_logging()
init_sentry()
log = get_logger(__name__)
settings = get_settings()

limiter = Limiter(key_func=get_remote_address)

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
