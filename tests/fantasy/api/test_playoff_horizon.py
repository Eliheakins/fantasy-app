"""The playoff-weeks horizon on the waivers job and the streamers table."""

from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from fastapi.testclient import TestClient
from store_fixture import write_rows
from test_api import wait_ok
from test_moves import league_with
from test_simulate_load import build_store

from fantasy import _market, data_api
from fantasy._engine import _league
from fantasy._schemas import ENGINE_SCHEMAS
from fantasy.sim.bracket import playoff_weeks


def late_player_league() -> Any:
    data = league_with([("early", "WR", 30.0), ("late", "WR", 30.0)])
    proj = data.projections.filter(
        ~(
            ((pl.col("gsis_id") == "early") & (pl.col("week") >= 8))
            | ((pl.col("gsis_id") == "late") & (pl.col("week") < 8))
        )
    )
    return replace(data, projections=proj)


def test_playoff_horizon_ranks_a_late_only_player_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_market, "_names", lambda d: {})
    monkeypatch.setattr(_market, "_trending_adds", lambda d: {})
    loaded = (late_player_league(), 1)
    ros = _market.waivers("t", loaded=loaded)
    playoffs = _market.waivers("t", loaded=loaded, horizon="playoffs")
    assert ros["gsis_id"][0] == "early"
    assert playoffs["gsis_id"][0] == "late"


def test_the_waivers_job_passes_the_horizon_and_caches_each_mode(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    def fake(league: str, horizon: str = "ros", **kwargs: Any) -> pl.DataFrame:
        seen.append(horizon)
        return pl.DataFrame(schema=ENGINE_SCHEMAS["waivers"])

    monkeypatch.setattr(data_api, "waivers", fake)
    for path in ("waivers", "waivers?horizon=playoffs", "waivers?horizon=ros", "waivers"):
        url = f"/api/leagues/t/{path}"
        wait_ok(client, partial(client.get, url))
    assert seen == ["ros", "playoffs"]  # each mode ran once; the repeats hit the cache
    assert client.get("/api/leagues/t/waivers?horizon=nope").status_code == 422


def test_streamers_sum_the_league_playoff_weeks(tmp_path: Path) -> None:
    build_store(tmp_path, [(100.0, 90.0)])
    data, _ = _league("t", tmp_path)
    first = data.playoff_start
    weeks = (3, first, first + 1, first + 5)  # this week, two playoff weeks, one after the final
    rows = [
        {
            "league_id": "L1",
            "kind": "K",
            "unit": "G_FREEK",
            "team": "KC",
            "week": w,
            "projection": v,
        }
        for w, v in zip(weeks, (1.0, 2.0, 4.0, 100.0), strict=True)
    ]
    write_rows(tmp_path, "streaming_projection", rows)
    out = data_api.streamers("t", "K", data_dir=tmp_path)
    assert out["playoff_points"].to_list() == [6.0]
    assert out["next_three"].to_list() == [1.0]


def test_league_rows_carry_the_bracket_length(tmp_path: Path) -> None:
    build_store(tmp_path, [(100.0, 90.0)])
    row = data_api.leagues(tmp_path).row(0, named=True)
    assert row["playoff_weeks"] == playoff_weeks(row["playoff_teams"])
