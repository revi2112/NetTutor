"""GET /health: reports whether the app can reach Postgres."""

import logging

import psycopg
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.db.connection import connect

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
def health(request: Request) -> JSONResponse:
    settings: Settings = request.app.state.settings
    try:
        with connect(settings.database_url) as conn:
            conn.execute("SELECT 1")
    except psycopg.OperationalError as exc:
        # Log only the error type: the message can contain the host or credentials.
        logger.warning("health check: database unreachable (%s)", type(exc).__name__)
        return JSONResponse(status_code=503, content={"status": "degraded", "db": "unreachable"})
    return JSONResponse(status_code=200, content={"status": "ok", "db": "ok"})
