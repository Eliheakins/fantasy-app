from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.deps import get_app_state
from core.state import AppState
from schemas.api import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(state: Annotated[AppState, Depends(get_app_state)]) -> HealthResponse:
    seasons = [s.season for s in state.manifest.seasons] if state.manifest else []
    return HealthResponse(
        status="ok" if seasons else "degraded",
        data_ready=bool(seasons),
        data_through=state.manifest.data_through if state.manifest else None,
        seasons=seasons,
    )
