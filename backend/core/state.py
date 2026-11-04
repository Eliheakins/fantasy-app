from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl
from openai import AsyncOpenAI

from schemas.api import PbpShard
from schemas.manifest import Manifest


@dataclass
class AppState:
    player_index: pl.DataFrame | None = None
    manifest: Manifest | None = None
    pbp_shards: list[PbpShard] = field(default_factory=list)
    llm_client: AsyncOpenAI | None = None


app_state = AppState()
