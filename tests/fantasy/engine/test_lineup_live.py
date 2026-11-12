"""Lineup mid-week: finished games count their points; a player who is out is not slotted."""

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from store_fixture import engine_store, patch_league
from test_data_api_characterization import NOW

from fantasy import _engine, data_api
from fantasy.sim.availability import EASTERN, GAME_MINUTES


def test_a_player_whose_game_is_over_stays_in_the_lineup_with_his_points(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine_store(tmp_path)
    data, _ = _engine._league("t", data_dir=tmp_path)
    # his projection is gone (no future game row) but his game finished with 17.5 points
    gone = data.projections.filter(pl.col("gsis_id") != "G_WR")
    patch_league(monkeypatch, projections=gone, live={"G_WR": (17.5, 0.0)})
    out = data_api.lineup("t", now=NOW, data_dir=tmp_path).filter(pl.col("gsis_id") == "G_WR")
    row = out.row(0, named=True)
    assert (row["projection"], row["actual"], row["game"]) == (17.5, 17.5, "Final")


def test_a_player_who_is_out_is_left_on_the_bench(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine_store(tmp_path)
    patch_league(monkeypatch, injuries={"G_WR": ("Out", "", "")})
    row = (
        data_api.lineup("t", now=NOW, data_dir=tmp_path)
        .filter(pl.col("gsis_id") == "G_WR")
        .row(0, named=True)
    )
    assert (row["slot"], row["recommended"]) == ("BN", False)


def test_the_cache_key_moves_with_the_clock_only_while_a_game_is_on() -> None:
    kickoff = datetime(2026, 10, 25, 13, 0, tzinfo=EASTERN)
    kicks = {"A": kickoff, "B": kickoff}
    at = lambda minutes: kickoff + timedelta(minutes=minutes)  # noqa: E731
    assert _engine._clock_bucket(kicks, at(-1)) == ""
    assert _engine._clock_bucket(kicks, at(10)) != _engine._clock_bucket(kicks, at(13))
    assert _engine._clock_bucket(kicks, at(10)) == _engine._clock_bucket(kicks, at(10.5))
    # the window outlasts the game by a few minutes so the last build sees it final
    assert _engine._clock_bucket(kicks, at(GAME_MINUTES + 2)) != ""
    assert _engine._clock_bucket(kicks, at(GAME_MINUTES + 30)) == ""


def test_a_player_mid_game_and_a_finished_one_keep_their_projection_inside_their_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine_store(tmp_path)
    # the QB banked 25 with 40% of his game left; the WR finished with 17.5
    patch_league(monkeypatch, live={"G_QB": (25.0, 0.4), "G_WR": (17.5, 0.0)})
    out = data_api.lineup("t", now=NOW, data_dir=tmp_path)
    qb = out.filter(pl.col("gsis_id") == "G_QB").row(0, named=True)
    wr = out.filter(pl.col("gsis_id") == "G_WR").row(0, named=True)
    assert qb["p10"] <= qb["projection"] <= qb["p90"]
    assert qb["p10"] >= 25.0  # points already scored cannot be lost
    assert (wr["p10"], wr["p90"]) == (17.5, 17.5)
