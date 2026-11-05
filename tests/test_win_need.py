"""sim_win_need: my playoff odds by wins in the next four games, display only."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
import pytest
from store_fixture import use_store
from test_league_view import LEAGUE, LID
from test_season import N_TEAMS, inputs
from test_simulate_load import build_store

from fantasy import store
from fantasy.sim.season import conditional_odds, simulate_season, win_need_odds
from fantasy.stages import simulate as sim
from fantasy.stages.simulate import load_league_data

EXISTING = ("sim_season", "sim_seeds", "sim_team_weeks", "sim_conditional")
# Digest of the four existing outputs on the fixture below, taken before win_need existed.
# Float columns are summed, rounded to 9 places.
GOLDEN: dict[str, Any] = {
    "sim_season": (6, {"p_playoffs": 6.0, "p_bye": 2.0, "p_title": 1.0, "exp_wins": 9.0}),
    "sim_seeds": (36, {"p": 6.0}),
    "sim_team_weeks": (72, {"exp_points": 60.931824803, "sd_points": 164.57373188}),
    "sim_conditional": (36, {"p_condition": 18.0, "p_playoffs": 36.0, "p_title": 6.0}),
}
# The same for simulate_season and conditional_odds on a larger league with a persistent shift.
GOLDEN_SEASON = [0.41875, 0.55275, 0.67075, 0.0165, 0.03025, 0.0515, 2.4105, 2.77775, 3.06325]
GOLDEN_CONDITIONAL = (448, {"p_condition": 224.0, "p_playoffs": 336.0, "p_title": 56.0})


def digest(table: pl.DataFrame) -> tuple[int, dict[str, float]]:
    floats = [c for c, t in table.schema.items() if t == pl.Float64]
    return table.height, {c: round(float(table[c].sum()), 9) for c in floats}


def run_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, pl.DataFrame]:
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)])
    written: list[dict[str, pl.DataFrame]] = []
    monkeypatch.setattr(store, "write_tables", lambda tables, *a, **k: written.append(tables))
    monkeypatch.setattr(sim, "append_history", lambda latest, *a, **k: latest)
    monkeypatch.setattr(
        sim, "load_league_data", lambda league, strict=True: load_league_data(LEAGUE)
    )
    use_store(monkeypatch, tmp_path)
    sim.run(n_sims=300)
    return written[0]


def test_existing_outputs_are_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tables = run_stage(tmp_path, monkeypatch)
    assert {name: digest(tables[name]) for name in EXISTING} == GOLDEN


def test_season_simulation_and_conditional_odds_are_unchanged() -> None:
    inp = inputs(np.linspace(90, 110, N_TEAMS), 20.0, n_sims=4000, shift_sd=5.0)
    res = simulate_season(inp)
    first = [*res.p_playoffs[:3], *res.p_title[:3], *res.exp_wins[:3]]
    assert first == pytest.approx(GOLDEN_SEASON, abs=1e-9)
    assert digest(conditional_odds(inp, res)) == GOLDEN_CONDITIONAL
    win_need_odds(inp, res)  # computing the table must not disturb a later run
    assert simulate_season(inp).p_playoffs[:3].tolist() == pytest.approx(GOLDEN_SEASON[:3])


def test_stage_writes_win_need_for_every_team(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    need = run_stage(tmp_path, monkeypatch)["sim_win_need"]
    assert need.columns == list(store.SCHEMAS["sim_win_need"])
    assert set(need["league_id"]) == {LID} and set(need["as_of_week"]) == {3}
    assert need["wins"].min() == 0


def test_rows_run_from_zero_to_four_wins_and_partition_the_runs() -> None:
    inp = inputs(np.full(N_TEAMS, 100.0), 20.0, n_sims=4000)
    need = win_need_odds(inp, simulate_season(inp))
    for rid in inp.roster_ids:
        mine = need.filter(pl.col("roster_id") == rid).sort("wins")
        assert set(mine["n_games"]) == {4}
        assert mine["wins"].to_list() == [0, 1, 2, 3, 4]
        assert mine["p_condition"].sum() == pytest.approx(1.0)
        assert mine["n_runs"].sum() == 4000


def test_conditional_odds_average_back_to_the_overall_odds() -> None:
    inp = inputs(np.linspace(90, 110, N_TEAMS), 20.0, n_sims=4000)
    res = simulate_season(inp)
    need = win_need_odds(inp, res)
    for t, rid in enumerate(inp.roster_ids):
        mine = need.filter(pl.col("roster_id") == rid)
        assert (mine["p_condition"] * mine["p_playoffs"]).sum() == pytest.approx(res.p_playoffs[t])


def test_more_wins_never_hurt_much() -> None:
    inp = inputs(np.full(N_TEAMS, 100.0), 20.0, n_sims=20000)
    mine = win_need_odds(inp, simulate_season(inp)).filter(pl.col("roster_id") == 1).sort("wins")
    odds = mine["p_playoffs"].to_list()
    assert all(b >= a - 0.02 for a, b in zip(odds, odds[1:], strict=False))
    assert odds[-1] > odds[0] + 0.2


def test_fewer_than_four_games_left_gives_rows_up_to_that_many() -> None:
    inp = inputs(np.full(N_TEAMS, 100.0), 20.0, n_sims=2000)
    late = replace(inp, pairs={w: p for w, p in inp.pairs.items() if w >= 6})
    need = win_need_odds(late, simulate_season(late))
    assert set(need["n_games"]) == {2}
    assert need["wins"].max() == 2
