import json
from pathlib import Path

import polars as pl
from store_fixture import write_rows
from test_simulate_load import MINE, PLAYERS, build_store

from fantasy import data_api


def stash_store(tmp_path: Path, settings: dict | None = None, fa_status: str | None = "IR") -> None:
    """Mine: te on IR, rb Out, dl Doubtful. Free agent fa has `fa_status`. IR players are
    "Inactive" in Sleeper's player list."""
    build_store(tmp_path, [(100.0, 90.0)])
    leagues = pl.read_parquet(next(tmp_path.rglob("leagues.parquet")))
    row = {**leagues.row(0, named=True), "settings": json.dumps(settings or {})}
    write_rows(tmp_path, "leagues", [row])
    flags = {s: fa_status if s == "fa" else inj for s, (_, inj, _) in PLAYERS.items()}
    players = [
        {
            "sleeper_id": s, "full_name": s, "position": pos, "team": "KC",
            "status": "Inactive" if flags[s] == "IR" else "Active",  # as Sleeper lists IR players
            "injury_status": flags[s],
        }
        for s, (pos, _, _) in PLAYERS.items()
    ]  # fmt: skip
    write_rows(tmp_path, "sleeper_players", players)
    base = pl.read_parquet(next(tmp_path.rglob("proj_baseline.parquet")))
    later = base.filter(pl.col("gsis_id") == "G_FA", pl.col("week") == 4)
    extra = [{**later.row(0, named=True), "week": w} for w in (8, 15)]
    write_rows(tmp_path, "proj_baseline", [*base.iter_rows(named=True), *extra])
    owned = [(1, s) for s in MINE] + [(2, "opp"), (2, "theirk")]
    rosters = [
        {"league_id": "L1", "roster_id": r, "sleeper_id": s, "is_ir": s == "te"} for r, s in owned
    ]
    write_rows(tmp_path, "rosters", rosters)


def test_free_agent_on_ir_lists_first_week_and_playoff_points(tmp_path: Path) -> None:
    stash_store(tmp_path)
    out = data_api.stash("t", data_dir=tmp_path)
    fa = next(r for r in out["rows"] if r["gsis_id"] == "G_FA")
    assert (fa["status"], fa["owner"], fa["is_mine"]) == ("IR", None, False)
    assert fa["first_week"] == 8  # four zero games from week 3, then a projection
    assert fa["playoff_points"] > 0  # week 15 is a playoff week


def test_inactive_ir_players_are_listed_mine_and_free(tmp_path: Path) -> None:
    stash_store(tmp_path)
    rows = {r["gsis_id"]: r for r in data_api.stash("t", data_dir=tmp_path)["rows"]}
    assert (rows["G_TE"]["status"], rows["G_TE"]["is_mine"], rows["G_TE"]["position"]) == (
        "IR", True, "TE",
    )  # fmt: skip
    assert (rows["G_FA"]["status"], rows["G_FA"]["is_mine"]) == ("IR", False)


def test_my_out_player_is_listed_as_mine_and_healthy_are_excluded(tmp_path: Path) -> None:
    stash_store(tmp_path)
    rows = data_api.stash("t", data_dir=tmp_path)["rows"]
    rb = next(r for r in rows if r["gsis_id"] == "G_RB")
    assert (rb["owner"], rb["is_mine"], rb["status"]) == ("Mine", True, "Out")
    ids = {r["gsis_id"] for r in rows}
    assert not ids & {"G_QB", "G_WR", "G_OPP"}  # healthy or Questionable
    assert "G_DL" not in ids  # Doubtful is not IR, PUP or Out


def test_free_agent_without_a_flag_is_excluded(tmp_path: Path) -> None:
    stash_store(tmp_path, fa_status=None)
    assert "G_FA" not in {r["gsis_id"] for r in data_api.stash("t", data_dir=tmp_path)["rows"]}


def test_open_slots_come_from_settings_and_default_to_zero(tmp_path: Path) -> None:
    stash_store(tmp_path, {"reserve_slots": 3})  # te is on IR: one used
    assert data_api.stash("t", data_dir=tmp_path)["open_ir_slots"] == 2
    stash_store(tmp_path)
    assert data_api.stash("t", data_dir=tmp_path)["open_ir_slots"] == 0


def test_ir_eligible_follows_reserve_allow_out(tmp_path: Path) -> None:
    stash_store(tmp_path, {"reserve_slots": 2})
    rows = {r["gsis_id"]: r for r in data_api.stash("t", data_dir=tmp_path)["rows"]}
    assert (rows["G_FA"]["ir_eligible"], rows["G_RB"]["ir_eligible"]) == (True, False)
    stash_store(tmp_path, {"reserve_slots": 2, "reserve_allow_out": 1})
    rows = {r["gsis_id"]: r for r in data_api.stash("t", data_dir=tmp_path)["rows"]}
    assert rows["G_RB"]["ir_eligible"] is True
