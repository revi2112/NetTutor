"""FastAPI app factory."""

from fastapi import FastAPI

from app.api.health import router as health_router
from app.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="NetTutor")
    app.state.settings = settings or get_settings()
    app.include_router(health_router)
    return app


app = create_app()
