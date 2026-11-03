from __future__ import annotations

import httpx
from conftest import FILTERS, STATS

from core.state import app_state
from schemas.api import PbpShard


async def test_search_returns_503_with_a_build_hint_when_the_index_is_missing(
    client: httpx.AsyncClient,
):
    app_state.player_index = None

    res = await client.get("/search", params={"q": "mahomes"})

    assert res.status_code == 503
    assert "build_data.py" in res.json()["detail"]


async def test_intent_returns_503_when_the_llm_client_is_not_initialized(
    client: httpx.AsyncClient,
):
    app_state.llm_client = None

    res = await client.post(
        "/nlq/intent",
        json={
            "question": "Mahomes passing yards",
            "stats": [s.model_dump() for s in STATS],
            "filters": [f.model_dump() for f in FILTERS],
        },
    )

    assert res.status_code == 503


async def test_pbp_shards_lists_what_the_app_discovered(client: httpx.AsyncClient):
    app_state.pbp_shards = [PbpShard(year=2023, path="/data/nfl_pbp_2023.parquet")]

    res = await client.get("/pbp/shards")

    assert res.json() == [{"year": 2023, "path": "/data/nfl_pbp_2023.parquet"}]


async def test_player_detail_returns_the_player_with_the_shard_list(client: httpx.AsyncClient):
    app_state.pbp_shards = [PbpShard(year=2023, path="/data/nfl_pbp_2023.parquet")]

    res = await client.get("/player/00-0033873")

    body = res.json()
    assert body["player"]["full_name"] == "Patrick Mahomes"
    assert [s["year"] for s in body["shards"]] == [2023]
