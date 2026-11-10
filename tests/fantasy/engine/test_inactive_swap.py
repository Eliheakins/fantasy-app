"""The swap plan on the lineup, kickoffs by player, and the long-term injury notes."""

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from store_fixture import write_rows
from test_data_api_characterization import NOW, _engine_store
from test_lineup_live import _with

from fantasy import _engine, _lineup, data_api, store
from fantasy.config import load_config
from fantasy.sim.availability import EASTERN
from fantasy.sim.injuries import Flag


def test_kickoffs_by_player_leave_out_players_with_no_team_or_no_game(tmp_path: Path) -> None:
    _engine_store(tmp_path)
    ids = store.read_table("id_map", "derived", tmp_path)
    extra = pl.DataFrame(
        {"sleeper_id": ["nt", "bye"], "gsis_id": ["G_NOTEAM", "G_BYE"], "nfl_team": [None, "NYJ"]}
    )
    store.write_table(
        "id_map", pl.concat([ids, extra], how="diagonal_relaxed"), "derived", tmp_path
    )
    game = {"game_type": "REG", "season": load_config().season, "week": 3}
    game |= {"gameday": "2026-09-20", "gametime": "13:00", "home_team": "KC", "away_team": "BUF"}
    write_rows(tmp_path, "nfl_schedules", [game])
    kicks = _lineup._kickoffs_by_player(3, data_dir=tmp_path)
    assert kicks["G_QB"] == datetime(2026, 9, 20, 13, 0, tzinfo=EASTERN)
    assert "G_NOTEAM" not in kicks and "G_BYE" not in kicks


def test_lineup_names_the_swap_for_a_questionable_starter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path)
    _with(monkeypatch, injuries={"G_WR": ("Questionable", "Hamstring", None)})
    sunday = datetime(2026, 9, 20, 13, 0, tzinfo=EASTERN)
    kicks = {"G_WR": sunday, "G_DL": sunday + timedelta(hours=3), "G_QB": sunday}
    monkeypatch.setattr(_lineup, "_kickoffs_by_player", lambda week, data_dir=None: kicks)
    rows = {
        r["gsis_id"]: r
        for r in data_api.lineup("t", now=NOW, data_dir=tmp_path).iter_rows(named=True)
    }
    assert (
        rows["G_WR"]["recommended"]
        and rows["G_WR"]["swap_in"] == _engine._names(data_dir=tmp_path)["G_DL"]
    )
    assert rows["G_QB"]["swap_in"] is None


def test_long_term_notes_say_out_at_least_four_games_unless_the_curve_gives_a_chance(
    tmp_path: Path,
) -> None:
    _engine_store(tmp_path)
    data, _ = _engine._league("t", data_dir=tmp_path)
    chances = pl.DataFrame(
        {
            "gsis_id": ["G_RB", "G_RB", "G_TE", "G_TE"],
            "week": [3, 4, 3, 4],
            "projection": [0.0, 0.4, 0.0, 0.0],
            "play_prob": [0.0, 0.04, 0.0, 0.0],
        }
    )
    flags: dict[str, Flag] = {"G_RB": ("IR", "Knee", None), "G_TE": ("PUP", None, None)}
    hurt = replace(data, injuries=flags, projections=chances)
    assert _engine._injury_note(hurt, "G_RB") == "IR (knee): 0% to play this game, 4% next game"
    assert _engine._injury_note(hurt, "G_TE") == "PUP, out at least 4 games"
    no_chances = replace(hurt, projections=chances.drop("play_prob"))
    assert _engine._injury_note(no_chances, "G_RB") == "IR (knee), out at least 4 games"
