from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import health, pbp, players
from core.config import get_settings
from core.lifecycle import lifespan
from nlq import router as nlq_router
from nlq_microscope import router as nlq_microscope_router
from nlq_unified import router as nlq_unified_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="NFL Stat API", lifespan=lifespan)

    app.include_router(health.router)
    app.include_router(pbp.router)
    app.include_router(players.router)
    app.include_router(nlq_router, tags=["nlq"])
    app.include_router(nlq_microscope_router)
    app.include_router(nlq_unified_router)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins_list(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Content-Range", "Content-Length", "Accept-Ranges"],
    )

    ds = settings.data_source.strip().lower() or "local"
    if ds == "local" and settings.data_dir.is_dir():
        app.mount("/data", StaticFiles(directory=str(settings.data_dir)), name="data")

    return app


app = create_app()
