"""The weeks-ahead lineup grid: starter per slot per week through the last playoff week."""

from pathlib import Path

import polars as pl
import pytest
from store_fixture import write_rows
from test_simulate_load import build_store

from fantasy import _engine, data_api
from fantasy.config import load_config

FAR_WEEKS = range(5, 18)
EXTRA_FREE = [f"x{i}" for i in range(4)]  # free wide receivers worth 30, 29, 28, 27


def grid_store(tmp_path: Path, *, free_wrs: bool = False, bye_week_4: bool = False) -> None:
    build_store(tmp_path, [(100.0, 90.0)])
    base = pl.read_parquet(next(tmp_path.rglob("proj_baseline.parquet")))
    template = base.filter(pl.col("gsis_id") == "G_QB", pl.col("week") == 4).row(0, named=True)
    rows = list(base.iter_rows(named=True))
    if bye_week_4:  # the quarterback has no row in his bye week
        rows = [r for r in rows if not (r["gsis_id"] == "G_QB" and r["week"] == 4)]
    far = [
        {**r, "week": w}
        for r in rows
        if r["week"] == 4 and r["gsis_id"] in ("G_QB", "G_WR", "G_RB")
        for w in FAR_WEEKS
    ]
    rows += far
    if free_wrs:
        players = pl.read_parquet(next(tmp_path.rglob("sleeper_players.parquet")))
        ids = pl.read_parquet(next(tmp_path.rglob("id_map.parquet")))
        new = [
            {"sleeper_id": f"s{x}", "full_name": x, "position": "WR", "team": "DAL",
             "status": "Active", "injury_status": None}
            for x in EXTRA_FREE
        ]  # fmt: skip
        write_rows(tmp_path, "sleeper_players", [*players.iter_rows(named=True), *new])
        mapped = [
            {"sleeper_id": f"s{x}", "gsis_id": f"G_{x}", "nfl_team": "DAL"} for x in EXTRA_FREE
        ]
        write_rows(tmp_path, "id_map", [*ids.iter_rows(named=True), *mapped])
        for i, x in enumerate(EXTRA_FREE):
            rows += [
                {**template, "gsis_id": f"G_{x}", "position": "WR", "team": "DAL", "week": w,
                 "projection": 30.0 - i}
                for w in (3, 4, *FAR_WEEKS)
            ]  # fmt: skip
    write_rows(tmp_path, "proj_baseline", rows)
    if bye_week_4:
        season = load_config().season
        games = [
            {"game_type": "REG", "season": season, "week": w, "home_team": h, "away_team": a,
             "gameday": "2026-11-15", "gametime": "13:00"}
            for w, h, a in ((3, "KC", "DAL"), (4, "DAL", "MIA"))
        ]  # fmt: skip
        write_rows(tmp_path, "nfl_schedules", games)
    _engine._clear_league_cache()


def cell(grid: dict, week: int, slot: str) -> dict:
    return next(r for r in grid["rows"] if r["week"] == week and r["slot"] == slot)


def test_weeks_run_from_current_through_the_last_playoff_week(tmp_path: Path) -> None:
    grid_store(tmp_path)
    grid = data_api.lineup_grid("t", data_dir=tmp_path)
    assert grid["weeks"] == list(range(3, 18))
    assert grid["playoff_weeks"] == [15, 16, 17]
    assert {r["week"] for r in grid["rows"]} == set(grid["weeks"])


def test_out_starter_is_flagged_out(tmp_path: Path) -> None:
    grid_store(tmp_path)
    rb = cell(data_api.lineup_grid("t", data_dir=tmp_path), 3, "RB")
    assert (rb["gsis_id"], rb["flag"]) == ("G_RB", "out")


def test_out_flag_follows_each_weeks_chance_of_playing(tmp_path: Path) -> None:
    grid_store(tmp_path)
    data, _ = _engine._league("t", data_dir=tmp_path)
    assert _engine._play_probs(data, 3)["G_RB"] < 0.5 <= _engine._play_probs(data, 6)["G_RB"]
    grid = data_api.lineup_grid("t", data_dir=tmp_path)
    assert cell(grid, 3, "RB")["flag"] == "out"
    assert (cell(grid, 6, "RB")["gsis_id"], cell(grid, 6, "RB")["flag"]) == ("G_RB", None)


def test_slot_whose_best_player_is_on_bye_is_flagged_bye(tmp_path: Path) -> None:
    grid_store(tmp_path, bye_week_4=True)
    grid = data_api.lineup_grid("t", data_dir=tmp_path)
    qb4 = cell(grid, 4, "QB")
    assert (qb4["gsis_id"], qb4["flag"], qb4["points"]) == (None, "bye", 0.0)
    assert cell(grid, 3, "QB")["flag"] is None


def test_starter_below_the_best_free_stand_in_is_weak(tmp_path: Path) -> None:
    grid_store(tmp_path, free_wrs=True)
    grid = data_api.lineup_grid("t", data_dir=tmp_path)
    wr = cell(grid, 4, "WR")
    assert (wr["points"], wr["flag"]) == (10.0, "weak")  # a 28-point stand-in is free
    assert cell(grid, 4, "QB")["flag"] is None  # no free quarterback to beat him


def test_grid_totals_match_the_schedule_in_regular_season_weeks(tmp_path: Path) -> None:
    grid_store(tmp_path, free_wrs=True)
    grid = data_api.lineup_grid("t", data_dir=tmp_path)
    sched = data_api.schedule("t", data_dir=tmp_path)
    assert sched.height > 0
    for week, mine in zip(sched["week"], sched["my_points"], strict=True):
        total = sum(r["points"] for r in grid["rows"] if r["week"] == week)
        assert total == pytest.approx(mine)


def test_every_week_lists_the_leagues_player_slots(tmp_path: Path) -> None:
    grid_store(tmp_path)
    rows = [r for r in data_api.lineup_grid("t", data_dir=tmp_path)["rows"] if r["week"] == 17]
    assert [r["slot"] for r in rows] == ["QB", "RB", "WR"]
