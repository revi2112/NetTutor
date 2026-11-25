"""FastAPI app factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI

from app.api.health import router as health_router
from app.config import Settings, get_settings
from app.db.connection import connect
from app.db.schema_check import check_schema

logger = logging.getLogger(__name__)


def _startup_check(settings: Settings) -> None:
    """Fail on an embedding mismatch; tolerate an unreachable DB so /health can report it."""
    try:
        conn = connect(settings.database_url)
    except psycopg.OperationalError as exc:
        logger.warning("startup: database unreachable (%s); continuing", type(exc).__name__)
        return
    with conn:
        check_schema(conn, settings.embed_model, settings.embed_dim)


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _startup_check(resolved)
        yield

    app = FastAPI(title="NetTutor", lifespan=lifespan)
    app.state.settings = resolved
    app.include_router(health_router)
    return app


app = create_app()
