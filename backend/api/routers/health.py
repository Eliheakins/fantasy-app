from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.deps import get_app_state
from core.state import AppState
from schemas.api import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(state: Annotated[AppState, Depends(get_app_state)]) -> HealthResponse:
    return HealthResponse(
        status="ok" if state.player_index is not None else "degraded",
        data_source=state.data_source,
        player_index_loaded=state.player_index is not None,
    )
