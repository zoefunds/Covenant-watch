"""Sentry init -- safe no-op if SENTRY_DSN is unset."""
from __future__ import annotations

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


def init_sentry() -> None:
    settings = get_settings()
    if not settings.SENTRY_DSN:
        log.info("sentry.disabled", reason="SENTRY_DSN not set")
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            environment=settings.ENV,
            integrations=[FastApiIntegration()],
            traces_sample_rate=0.1,
        )
        log.info("sentry.enabled")
    except Exception:  # pragma: no cover - defensive, never crash startup over Sentry
        log.exception("sentry.init_failed")
