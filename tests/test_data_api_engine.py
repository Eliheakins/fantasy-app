from pathlib import Path

import polars as pl
import pytest
from store_fixture import write_rows
from test_simulate_load import build_store

from fantasy import data_api


def test_waivers_never_suggest_a_rostered_player(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)])
    write_rows(tmp_path, "trending")
    out = data_api.waivers("t")
    rostered = {"G_QB", "G_RB", "G_WR", "G_TE", "G_DL", "G_OPP"}
    assert not rostered & set(out["gsis_id"].to_list())
    assert set(out["gsis_id"].to_list()) <= {"G_FA"}


def test_trade_roster_changes_pick_up_a_free_agent_when_i_give_two_for_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)])
    write_rows(tmp_path, "trending")
    out = data_api.trade_roster_changes("t", 2, ["G_QB", "G_WR"], ["G_OPP"])
    mine = out.filter(pl.col("team_name") == "Mine")
    assert mine["action"].to_list() == ["picked up"] and mine["full_name"].to_list() == ["fa"]


def test_a_lopsided_trade_in_my_favor_raises_my_expected_wins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)])
    out = data_api.evaluate_trade("t", 2, ["G_RB"], ["G_OPP"])  # my Out player for a healthy one
    me = out.filter(pl.col("side") == "me").row(0, named=True)
    them = out.filter(pl.col("side") == "them").row(0, named=True)
    assert me["roster_id"] == 1 and them["roster_id"] == 2
    assert me["wins_after"] > me["wins_before"]
    assert them["wins_after"] < them["wins_before"]


def test_trade_after_the_deadline_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)], trade_deadline=2)
    with pytest.raises(ValueError, match="deadline"):
        data_api.evaluate_trade("t", 2, ["G_RB"], ["G_OPP"])


def test_streamers_list_free_kickers_and_mine_but_never_another_teams(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)])
    rows = [
        {"league_id": "L1", "kind": "K", "unit": u, "team": "KC", "week": 3, "projection": p}
        for u, p in (("G_K", 6.0), ("G_FREEK", 9.0), ("G_THEIRK", 12.0))
    ]
    write_rows(tmp_path, "streaming_projection", rows)
    # leagues() binds its data_dir default at import, so point it at the fixture store
    original = data_api.leagues
    monkeypatch.setattr(data_api, "leagues", lambda data_dir=tmp_path: original(data_dir))
    out = data_api.streamers("t", "K")
    assert out["unit"].to_list() == ["G_FREEK", "G_K"]
    assert out["is_mine"].to_list() == [False, True]


def test_trade_roster_changes_show_a_drop_that_lands_on_a_player_just_received(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)])
    write_rows(tmp_path, "trending")
    real = data_api.moves.apply_trade

    def drop_received(*args, **kwargs):
        return real(*args, **kwargs).filter(pl.col("gsis_id") != "G_OPP")

    monkeypatch.setattr(data_api.moves, "apply_trade", drop_received)
    out = data_api.trade_roster_changes("t", 2, ["G_RB"], ["G_OPP"])
    dropped = out.filter((pl.col("team_name") == "Mine") & (pl.col("action") == "dropped"))
    assert dropped["full_name"].to_list() == ["opp"]
