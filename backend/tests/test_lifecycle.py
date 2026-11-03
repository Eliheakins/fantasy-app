from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import FastAPI

from core import lifecycle
from core.state import app_state


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    fake = SimpleNamespace(
        data_dir=tmp_path,
        player_index_path=tmp_path / "player_index.parquet",
        # Port 9 refuses connections, so the keep-alive ping fails fast and is ignored.
        llm_base_url="http://127.0.0.1:9/v1",
        llm_model="m",
        llm_timeout_seconds=1.0,
    )
    monkeypatch.setattr(lifecycle, "get_settings", lambda: fake)
    yield fake
    app_state.player_index = None
    app_state.pbp_shards = []
    app_state.llm_client = None


async def test_lifespan_loads_index_and_shards_and_starts_the_client(settings: SimpleNamespace):
    pl.DataFrame({"gsis_id": ["1"], "full_name": ["A B"]}).write_parquet(settings.player_index_path)
    (settings.data_dir / "nfl_pbp_2023.parquet").touch()

    async with lifecycle.lifespan(FastAPI()):
        assert app_state.player_index is not None
        assert app_state.player_index.height == 1
        assert [s.year for s in app_state.pbp_shards] == [2023]
        assert app_state.llm_client is not None

    assert app_state.llm_client is None


async def test_lifespan_starts_degraded_when_the_player_index_is_missing(settings: SimpleNamespace):
    async with lifecycle.lifespan(FastAPI()):
        assert app_state.player_index is None
        assert app_state.pbp_shards == []
        assert app_state.llm_client is not None
