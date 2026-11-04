from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import health, nlq
from core.config import CORS_ORIGINS, get_settings
from core.lifecycle import lifespan


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="NFL Stat API", lifespan=lifespan)

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


app = create_app()
