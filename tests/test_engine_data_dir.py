from pathlib import Path

import polars as pl
from store_fixture import write_rows
from test_simulate_load import build_store

from fantasy import _engine


def test_build_league_reads_the_data_dir_it_is_keyed_on(tmp_path: Path) -> None:
    build_store(tmp_path, [(100.0, 90.0)])
    data, mine = _engine._build_league("t", "v1", str(tmp_path))
    assert data.league_id == "L1" and mine == 1


def test_optional_tables_of_the_build_come_from_the_given_data_dir(tmp_path: Path) -> None:
    build_store(tmp_path, [(100.0, 90.0)])
    base, _ = _engine._build_league("t", "v1", str(tmp_path))
    curve = {"league_id": "L1", "position": "QB", "center": 10.0, "factor": 0.5, "n": 100}
    write_rows(tmp_path, "projection_calibration", [curve])
    calibrated, _ = _engine._build_league("t", "v2", str(tmp_path))
    before = base.projections.filter(pl.col("gsis_id") == "G_QB")["projection"].to_list()
    after = calibrated.projections.filter(pl.col("gsis_id") == "G_QB")["projection"].to_list()
    assert after != before


def test_league_cache_is_keyed_by_data_dir(tmp_path: Path) -> None:
    first, second = tmp_path / "a", tmp_path / "b"
    build_store(first, [(100.0, 90.0)])
    build_store(second, [(100.0, 90.0)])
    _engine._clear_league_cache()
    assert _engine._league("t", first)[0] is not _engine._league("t", second)[0]
    assert _engine._league("t", first)[0] is _engine._league("t", first)[0]


def test_the_app_reads_the_data_dir_it_was_built_on_and_the_team_param(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from fantasy import api

    build_store(tmp_path, [(100.0, 90.0)])
    with TestClient(api.create_app(data_dir=tmp_path), base_url="http://localhost") as client:
        mine = client.get("/api/leagues/t/teams").json()["data"]
        assert [r["team_name"] for r in mine if r["is_me"]] == ["Mine"]
        assert client.app.state.data_dir == tmp_path  # type: ignore[attr-defined]
        rows = client.get("/api/leagues/t/season-odds?team=2").json()
        assert rows["status"] == "ok"
