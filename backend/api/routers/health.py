from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.deps import get_app_state, get_settings_dep
from core.config import AppSettings
from core.manifest_state import refresh_manifest
from core.state import AppState
from schemas.api import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(
    state: Annotated[AppState, Depends(get_app_state)],
    settings: Annotated[AppSettings, Depends(get_settings_dep)],
) -> HealthResponse:
    refresh_manifest(state, settings.data_dir)
    seasons = [s.season for s in state.manifest.seasons] if state.manifest else []
    # The app needs the player list as well as the shards.
    ready = bool(seasons) and state.manifest is not None and state.manifest.players is not None
    return HealthResponse(
        status="ok" if ready else "degraded",
        data_ready=ready,
        data_through=state.manifest.data_through if state.manifest else None,
        seasons=seasons,
    )
