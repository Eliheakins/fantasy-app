from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from nfl_stat.api.routers import health, nlq
from nfl_stat.core.config import CORS_ORIGINS, AppSettings, get_settings
from nfl_stat.core.lifecycle import lifespan
from nfl_stat.core.state import AppState


def create_app(settings: AppSettings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="NFL Stat API", lifespan=lifespan)
    app.state.settings = settings
    app.state.app_state = AppState()

    app.include_router(health.router)
    app.include_router(nlq.router)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        # The browser engine reads Parquet columns via HTTP range requests.
        expose_headers=["Content-Range", "Content-Length", "Accept-Ranges"],
    )

    if settings.data_dir.is_dir():
        app.mount("/data", StaticFiles(directory=str(settings.data_dir)), name="data")

    return app
