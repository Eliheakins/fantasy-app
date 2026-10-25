"""League page reads (power rankings, luck, grades, what-if) and the tables the stage writes."""

from pathlib import Path
from typing import Any

import polars as pl
import pytest
from store_fixture import use_store, write_rows
from test_simulate_load import LEAGUE, build_store

from fantasy import data_api, store
from fantasy.sim.odds import build_inputs
from fantasy.stages import simulate as sim
from fantasy.stages.simulate import load_league_data

LID = "L1"
POSITIONS = ["QB", "RB", "K", "BN", "BN"]
# weeks 1 and 2 scored; later weeks are the zero-point placeholders Sleeper pre-fills
SCORES = {1: {1: 100.0, 2: 90.0, 3: 80.0, 4: 70.0}, 2: {1: 60.0, 3: 95.0, 2: 75.0, 4: 75.0}}
PAIRS = {1: [(1, 2), (3, 4)], 2: [(1, 3), (2, 4)], 3: [(1, 4), (2, 3)], 4: [(1, 2), (3, 4)]}


@pytest.fixture
def league(tmp_path: Path) -> Path:
    write_rows(
        tmp_path,
        "leagues",
        [
            {
                "league_key": "t",
                "league_id": LID,
                "current_week": 3,
                "playoff_week_start": 10,
                "roster_positions": POSITIONS,
                "scoring_settings": "{}",
            }
        ],
    )
    teams = [
        {"league_id": LID, "roster_id": r, "team_name": f"T{r}", "is_me": r == 1}
        for r in range(1, 5)
    ]
    write_rows(tmp_path, "league_teams", teams)
    rows = []
    for week, pairs in PAIRS.items():
        for m, pair in enumerate(pairs, start=1):
            rows += [
                {"league_id": LID, "week": week, "roster_id": r, "matchup_id": m}
                | {"points": SCORES.get(week, {}).get(r, 0.0)}
                for r in pair
            ]
    write_rows(tmp_path, "matchups", rows)
    write_rows(
        tmp_path,
        "sleeper_players",
        [
            {"sleeper_id": s, "position": p, "fantasy_positions": [p]}
            for s, p in (("qb1", "QB"), ("rb1", "RB"), ("rb2", "RB"), ("k1", "K"), ("ir", "WR"))
        ],
    )
    players = [
        # sleeper_id, points, is_starter
        ("qb1", 20.0, True), ("rb1", 10.0, True), ("rb2", 15.0, False), ("k1", 5.0, True),
        ("ir", None, False),
    ]  # fmt: skip
    write_rows(
        tmp_path,
        "matchup_players",
        [
            {"league_id": LID, "week": w, "roster_id": 1, "sleeper_id": s, "points": p}
            | {"is_starter": st}
            for w in (1, 2)
            for s, p, st in players
        ],
    )
    return tmp_path


def sim_tables(path: Path) -> None:
    odds = [(1, 0.7, 0.2), (2, 0.5, 0.1), (3, 0.9, 0.5), (4, 0.3, 0.1)]
    write_rows(
        path,
        "sim_season",
        [
            {"league_id": LID, "roster_id": r, "team_name": f"T{r}", "as_of_week": 3}
            | {"p_playoffs": po, "p_title": pt, "exp_wins": 4.0}
            for r, po, pt in odds
        ],
    )
    now = {1: 100.0, 2: 90.0, 3: 120.0, 4: 80.0}
    weeks = [
        {
            "league_id": LID,
            "roster_id": r,
            "week": w,
            "as_of_week": 3,
            "exp_points": now[r] if w == 3 else 100.0,
        }
        for r in now
        for w in (3, 4)
    ]
    write_rows(path, "sim_team_weeks", weeks)
    cond = [
        # winner, loser, roster, n_runs, p_condition, p_playoffs, p_title
        (1, 4, 1, 12000, 0.6, 0.8, 0.25),
        (4, 1, 1, 8000, 0.4, 0.5, 0.1),
        (2, 3, 1, 500, 0.025, 0.9, 0.3),
        (3, 2, 1, 19500, 0.975, 0.69, 0.2),
        (1, 4, 2, 12000, 0.6, 0.5, 0.1),
    ]
    write_rows(
        path,
        "sim_conditional",
        [
            {"league_id": LID, "as_of_week": 3, "week": 3, "winner_id": w, "loser_id": lo}
            | {"roster_id": r, "n_runs": n, "p_condition": pc, "p_playoffs": pp, "p_title": pt}
            for w, lo, r, n, pc, pp, pt in cond
        ],
    )


def test_luck_compares_actual_wins_to_the_all_play_expectation(league: Path) -> None:
    out = data_api.luck("t", league)
    row = {r["roster_id"]: r for r in out.iter_rows(named=True)}
    assert row[3]["luck"] == pytest.approx(2 - 4 / 6 * 2)
    assert (row[3]["ap_wins"], row[3]["ap_losses"], row[3]["weeks"]) == (4, 2, 2)
    assert row[1]["luck"] == pytest.approx(0.0) and row[1]["is_me"]
    assert out["luck"].to_list() == sorted(out["luck"].to_list(), reverse=True)


def test_luck_skips_the_current_week_and_unknown_leagues(league: Path) -> None:
    # week 3 has points once played; it is not complete until the current week moves past it
    assert data_api.luck("t", league)["weeks"].max() == 2
    assert data_api.luck("nope", league).columns == data_api.luck("t", league).columns


def test_manager_grades_compare_started_points_to_the_hindsight_best(league: Path) -> None:
    out = data_api.manager_grades("t", league)
    assert out["roster_id"].to_list() == [1]  # only rosters with player rows are graded
    row = out.row(0, named=True)
    assert (row["actual_points"], row["optimal_points"], row["weeks"]) == (70.0, 80.0, 2)
    assert row["efficiency"] == pytest.approx(0.875) and row["bench_points_left"] == 10.0


def test_power_rankings_order_by_expected_score_and_rank_remaining_schedule(league: Path) -> None:
    sim_tables(league)
    out = data_api.power_rankings("t", league)
    got = {r["roster_id"]: r for r in out.iter_rows(named=True)}
    assert out["roster_id"].to_list() == [3, 1, 2, 4] and out["rank"].to_list() == [1, 2, 3, 4]
    assert [got[r]["sos_remaining"] for r in (1, 2, 3, 4)] == [90.0, 110.0, 95.0, 100.0]
    assert [got[r]["sos_rank"] for r in (2, 4, 3, 1)] == [1, 2, 3, 4]  # 1 is the toughest
    assert got[1]["is_me"] and not got[2]["is_me"]


def test_power_rankings_are_empty_before_the_simulation_has_run(league: Path) -> None:
    out = data_api.power_rankings("t", league)
    assert out.is_empty() and "sos_rank" in out.columns


def test_what_if_gives_my_deltas_against_the_plain_odds_my_game_first(league: Path) -> None:
    sim_tables(league)
    out = data_api.what_if("t", 0, league)
    assert out.height == 4  # only my roster's rows
    first = out.row(0, named=True)
    assert (first["winner_id"], first["loser_id"], first["involves_me"]) == (1, 4, True)
    assert first["d_playoffs"] == pytest.approx(0.1) and first["d_title"] == pytest.approx(0.05)
    assert first["n_runs"] == 12000 and first["winner"] == "T1"
    assert out["involves_me"].to_list() == [True, True, False, False]
    small = out.filter(pl.col("n_runs") < 1000)
    assert small.height == 1  # kept in the data: the page hides it and says why


def test_what_if_is_empty_for_a_completed_or_playoff_week_and_missing_tables(league: Path) -> None:
    assert data_api.what_if("t", 3, league).is_empty()  # no sim tables yet
    sim_tables(league)
    assert data_api.what_if("t", 2, league).is_empty()
    assert data_api.what_if("t", 10, league).is_empty()
    assert data_api.what_if("t", 4, league).is_empty()  # nothing precomputed for week 4


def test_team_week_rows_hold_expected_points_with_the_shift_for_regular_weeks_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)])
    data = load_league_data(LEAGUE)
    inp = build_inputs(data, None, 200, 0)
    rows = sim.team_week_rows(data, inp)
    weeks = {r[2] for r in rows}
    assert weeks == set(range(data.current_week, data.playoff_start))  # no playoff weeks
    first = next(r for r in rows if r[1] == inp.roster_ids[0] and r[2] == data.current_week)
    assert first[4] == pytest.approx(inp.mean[0, 0] + inp.shift[0, 0].mean())
    assert first[5] >= inp.noise_sd[0, 0]


def test_run_writes_the_new_tables_in_one_call_with_the_season_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)])
    written: list[dict[str, pl.DataFrame]] = []
    monkeypatch.setattr(store, "write_tables", lambda tables, *a, **k: written.append(tables))
    monkeypatch.setattr(sim, "append_history", lambda latest, *a, **k: latest)
    monkeypatch.setattr(
        sim, "load_league_data", lambda league, strict=True: load_league_data(LEAGUE)
    )
    use_store(monkeypatch, tmp_path)
    latest = sim.run(n_sims=300)
    assert len(written) == 1
    tables: dict[str, Any] = written[0]
    assert set(tables) == {"sim_season", "sim_seeds", "sim_team_weeks", "sim_conditional"}
    assert tables["sim_season"].equals(latest)
    cond = tables["sim_conditional"]
    assert set(cond["league_id"]) == {LID} and set(cond["as_of_week"]) == {3}
    assert tables["sim_team_weeks"]["week"].max() < 15
