"""Game-day history: one row per live tick (and manual refresh) for the current week only."""

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest
from fastapi.testclient import TestClient
from store_fixture import write_rows
from test_api import body

from fantasy import _live, api, data_api, store

T1 = datetime(2026, 9, 6, 17, 0, tzinfo=UTC)
T2 = datetime(2026, 9, 6, 17, 10, tzinfo=UTC)


@pytest.fixture
def store_dir(store_dir: Path) -> Path:
    """The API fixture store plus set starters in week 3, so both sides have points to come."""
    starters = [(1, "qb"), (2, "opp")]
    rows = [
        {"league_id": "L1", "week": 3, "roster_id": r, "sleeper_id": s, "is_starter": True}
        | {"points": 0.0}
        for r, s in starters
    ]
    write_rows(store_dir, "matchup_players", rows)
    return store_dir


def history(path: Path) -> pl.DataFrame:
    return store.read_table("live_win_history", "derived", path)


def test_a_tick_appends_my_row_from_the_current_simulation(
    store_dir: Path,
) -> None:
    data_api.record_live_tick(T1, store_dir)
    row = history(store_dir).row(0, named=True)
    assert (row["league_id"], row["roster_id"], row["week"]) == ("L1", 1, 3)
    assert row["run_at"] == T1.isoformat(timespec="seconds")
    assert 0.0 < row["win_prob"] < 1.0
    assert row["opp_projected"] > 0 and row["my_left"] >= 0


def test_the_same_run_at_is_not_added_twice(store_dir: Path) -> None:
    data_api.record_live_tick(T1, store_dir)
    data_api.record_live_tick(T1, store_dir)
    data_api.record_live_tick(T2, store_dir)
    assert history(store_dir)["run_at"].to_list() == [
        T1.isoformat(timespec="seconds"),
        T2.isoformat(timespec="seconds"),
    ]


def test_rows_of_an_earlier_week_are_dropped_on_the_next_append(
    store_dir: Path,
) -> None:
    data_api.record_live_tick(T1, store_dir)
    old = history(store_dir).with_columns(pl.lit(2, dtype=pl.Int64).alias("week"))
    store.write_table("live_win_history", old, "derived", store_dir)
    data_api.record_live_tick(T2, store_dir)
    assert history(store_dir)["week"].to_list() == [3]


def test_a_tick_never_touches_the_season_history_archive(store_dir: Path) -> None:
    path = store.table_path("sim_season_history", "archive", store_dir)
    before = path.read_bytes()
    data_api.record_live_tick(T1, store_dir)
    assert path.read_bytes() == before


def test_a_failing_league_is_logged_and_the_other_still_records(
    store_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    real = data_api.live_win_row

    def flaky(league_key: str, data_dir: Path) -> dict | None:
        if league_key == "bad":
            raise RuntimeError("boom")
        return real(league_key, data_dir)

    monkeypatch.setattr(_live, "live_win_row", flaky)
    leagues = store.read_table("leagues", "raw", store_dir)
    bad = leagues.with_columns(pl.lit("bad").alias("league_key"), pl.lit("L2").alias("league_id"))
    store.write_table("leagues", pl.concat([bad, leagues]), "raw", store_dir)
    data_api.record_live_tick(T1, store_dir)
    assert "live history failed for bad" in caplog.text
    assert history(store_dir)["league_id"].to_list() == ["L1"]


def test_a_failing_leagues_read_is_logged_not_raised(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "leagues.parquet").write_bytes(b"not parquet")
    data_api.record_live_tick(T1, tmp_path)
    assert "live history failed" in caplog.text


def test_all_leagues_are_written_in_one_write(
    store_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writes: list[int] = []
    real = store.write_table

    def counting(name: str, df: pl.DataFrame, *a: object, **k: object) -> Path:
        if name == "live_win_history":
            writes.append(len(df))
        return real(name, df, *a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(store, "write_table", counting)
    leagues = store.read_table("leagues", "raw", store_dir)
    store.write_table("leagues", pl.concat([leagues, leagues]), "raw", store_dir)
    data_api.record_live_tick(T1, store_dir)
    assert writes == [1]  # the second "league" has the same (league, roster, run_at) key


def test_dropping_an_old_week_leaves_other_leagues_rows_alone(store_dir: Path) -> None:
    data_api.record_live_tick(T1, store_dir)
    other = history(store_dir).with_columns(
        pl.lit("L2").alias("league_id"), pl.lit(2, dtype=pl.Int64).alias("week")
    )
    store.write_table(
        "live_win_history", pl.concat([history(store_dir), other]), "derived", store_dir
    )
    data_api.record_live_tick(T2, store_dir)
    kept = history(store_dir)
    assert sorted(set(zip(kept["league_id"], kept["week"], strict=True))) == [("L1", 3), ("L2", 2)]


def test_a_refresh_without_the_csrf_header_is_rejected_and_records_nothing(
    store_dir: Path,
) -> None:
    with TestClient(api.create_app(data_dir=store_dir), base_url="http://localhost") as bare:
        assert bare.post("/api/live/refresh").status_code == 403
    assert not store.table_path("live_win_history", "derived", store_dir).exists()


def test_route_returns_current_numbers_and_the_days_history(
    client: TestClient, store_dir: Path
) -> None:
    data_api.record_live_tick(T1, store_dir)
    out = body(client.get("/api/leagues/t/game-day"))["data"]
    assert out["week"] == 3
    assert out["as_of"]
    assert [h["run_at"] for h in out["history"]] == [T1.isoformat(timespec="seconds")]
    current = out["current"]
    assert current["my_team"] == "Mine" and current["opp_team"] == "Theirs"
    expected = current["opp_projected"] - current["my_points"]
    assert current["points_needed"] == pytest.approx(expected)


def test_route_for_another_team_has_no_history_of_mine(client: TestClient, store_dir: Path) -> None:
    data_api.record_live_tick(T1, store_dir)
    out = body(client.get("/api/leagues/t/game-day?team=2"))["data"]
    assert out["history"] == []
    assert out["current"]["my_team"] == "Theirs"


def test_route_rejects_unknown_league_and_team(client: TestClient) -> None:
    for path in ("/api/leagues/zzz/game-day", "/api/leagues/t/game-day?team=99"):
        assert body(client.get(path))["error"]["code"] == "invalid"


def test_manual_refresh_records_a_row_too(
    client: TestClient,
    store_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_live, "refresh_live", lambda data_dir: 1)
    assert body(client.post("/api/live/refresh"))["status"] == "ok"
    assert len(history(store_dir)) == 1
