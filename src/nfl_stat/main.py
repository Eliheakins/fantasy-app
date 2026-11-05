from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.types import Scope

from nfl_stat.api.routers import health, nlq
from nfl_stat.core.config import AppSettings, get_settings
from nfl_stat.core.lifecycle import lifespan
from nfl_stat.core.state import AppState

API_PREFIX = "/api/stat"
DATA_MOUNT = f"{API_PREFIX}/data"
PUBLIC_JSON = ("manifest.json", "players.json")


class ShardFiles(StaticFiles):
    """Serves only what the browser reads: the manifest, the player list and Parquet shards."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        if path not in PUBLIC_JSON and not path.endswith(".parquet"):
            raise HTTPException(status_code=404)
        return await super().get_response(path, scope)


def attach(app: FastAPI, settings: AppSettings) -> None:
    """Add the stat routes and the data shards to an app that owns its lifespan and guards.

    The host app must enter `nfl_stat.core.lifecycle.lifespan` and mount this before any
    catch-all route. Only `settings.data_dir` is served, never its parent.
    """
    app.state.stat_settings = settings
    app.state.stat_state = AppState()
    app.include_router(health.router, prefix=API_PREFIX)
    app.include_router(nlq.router, prefix=API_PREFIX)
    # check_dir off: the folder may be built while the server runs.
    app.mount(
        DATA_MOUNT, ShardFiles(directory=settings.data_dir, check_dir=False), name="stat-data"
    )


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """A stat-only app (used by the stat tests)."""
    app = FastAPI(title="NFL Stat API", lifespan=lifespan)
    attach(app, settings or get_settings())
    return app
