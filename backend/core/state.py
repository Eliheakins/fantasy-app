from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl
from openai import AsyncOpenAI

from schemas.api import PbpShard


@dataclass
class AppState:
    player_index: pl.DataFrame | None = None
    data_source: str = "local"
    pbp_shards: list[PbpShard] = field(default_factory=list)
    cfb_pbp_shards: list[PbpShard] = field(default_factory=list)
    openai_client: AsyncOpenAI | None = None


app_state = AppState()
