from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from api.deps import get_nfl_pbp_shards
from schemas.api import PbpShard

router = APIRouter(tags=["pbp"])


@router.get("/pbp/shards", response_model=list[PbpShard])
async def list_pbp_shards(
    shards: Annotated[list[PbpShard], Depends(get_nfl_pbp_shards)],
) -> list[PbpShard]:
    """Season shards (`/data/...` paths) for DuckDB-WASM."""
    return shards
