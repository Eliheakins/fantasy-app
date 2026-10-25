"""Need-based trade finder: positional need and surplus, need fit, acceptance, ranking."""

from dataclasses import replace

import polars as pl
import pytest
from test_moves import league_with
from test_odds import WEEKS

from fantasy.sim import moves
from fantasy.sim.odds import LeagueData


def need_league() -> LeagueData:
    """Team 1 has no WR2 and two spare RBs; team 2 has no RB2 and two spare WRs."""
    data = league_with(
        [("fa_wr", "WR", 4.0), ("fa_rb", "RB", 4.0), ("fa_te", "TE", 3.0), ("fa_qb", "QB", 8.0)]
    )
    extra = [(1, "t1_rb3", "RB", 14.0), (1, "t1_rb4", "RB", 14.0)]
    extra += [(2, "t2_wr3", "WR", 13.0), (2, "t2_wr4", "WR", 13.0)]
    proj_rows = [(g, w, v) for _, g, _, v in extra for w in WEEKS]
    proj = pl.concat(
        [data.projections, pl.DataFrame(proj_rows, schema=data.projections.schema, orient="row")]
    )
    added = pl.DataFrame(
        [(r, g, p) for r, g, p, _ in extra], schema=data.rosters.schema, orient="row"
    )
    kept = data.rosters.filter(~pl.col("gsis_id").is_in(["t1_wr2", "t2_rb2"]))
    return replace(data, projections=proj, rosters=pl.concat([kept, added]))


def team_needs(data: LeagueData, roster_id: int) -> moves.TeamNeeds:
    valuer = moves.Valuer(data)
    return moves.TeamNeeds(valuer, moves.team_ids(data, roster_id), moves.benchmarks(data, valuer))


def test_need_is_largest_where_the_team_has_a_hole() -> None:
    needs = team_needs(need_league(), 1).need
    assert needs["WR"] > 50 and needs["WR"] > 10 * needs["RB"]  # no WR2; RBs covered
    assert team_needs(need_league(), 2).need["RB"] > 50


def test_giving_up_a_bench_surplus_player_costs_nothing_and_a_starter_costs_points() -> None:
    team = team_needs(need_league(), 1)
    assert team.cost(("t1_rb4",)) == pytest.approx(0.0, abs=1e-6)
    assert team.cost(("t1_qb",)) > 100


def test_a_cross_position_swap_fills_need_and_a_same_position_swap_scores_zero() -> None:
    data = need_league()
    mine, theirs = team_needs(data, 1), team_needs(data, 2)
    fit, fills = mine.fit(("t1_rb4",), ("t2_wr4",))
    assert fit > 50 and fills == ["WR"]
    assert theirs.fit(("t2_wr4",), ("t1_rb4",))[0] > 50
    assert mine.fit(("t1_rb4",), ("t2_rb1",)) == (0.0, [])


def test_a_player_at_a_position_without_need_earns_no_credit() -> None:
    data = need_league()
    assert team_needs(data, 1).gain("t2_wr4") > 50
    assert team_needs(data, 1).fit(("t1_rb4",), ("t2_qb",))[0] < 1.0  # QB is no need


def test_candidate_pool_has_the_surplus_bench_player_and_no_duplicates() -> None:
    data = need_league()
    pool = team_needs(data, 1).pool(moves.ros_value(data, moves.team_ids(data, 1)))
    assert "t1_rb4" in pool or "t1_rb3" in pool
    assert len(pool) == len(set(pool))


def test_accept_takes_small_costs_for_need_and_rejects_beyond_the_tolerance() -> None:
    tol = moves.ODDS_TOL
    zero = {"my_playoff": 0.0, "my_title": 0.0, "their_playoff": 0.0, "their_title": 0.0}
    both = {**zero, "my_playoff": 0.01, "their_title": 0.01}
    assert moves.swap_kind(both, -5.0, -5.0) == "win-win"  # odds rise: need fit not required
    edge = {**zero, "my_playoff": -tol}
    assert moves.swap_kind(edge, 5.0, 5.0) == "need swap"  # exactly at the tolerance
    assert moves.swap_kind({**edge, "my_playoff": -tol - 1e-6}, 5.0, 5.0) is None
    assert moves.swap_kind(edge, 5.0, 1.0) is None  # partner gets no need fit
    assert moves.swap_kind(edge, -1.0, 5.0) is None


def test_ranking_puts_the_higher_need_fit_first_at_equal_odds() -> None:
    odds = {"my_title": 0.02, "my_playoff": 0.02}
    rows = [
        {"my_fit": 0.0, "their_fit": 0.0, **odds},
        {"my_fit": 90.0, "their_fit": 4.0, **odds},
        {"my_fit": 40.0, "their_fit": 30.0, **odds},
    ]
    ordered = sorted(rows, key=moves.rank_key)
    assert [r["my_fit"] for r in ordered] == [40.0, 90.0, 0.0]


def test_finder_returns_labelled_need_swaps_with_the_new_columns() -> None:
    found = moves.find_trades(need_league(), 1, n_sims=4000)
    assert found.schema == pl.Schema(moves.FINDER_COLUMNS)
    assert set(found["kind"]) <= {"win-win", "need swap"}
    cross = [
        r
        for r in found.iter_rows(named=True)
        if r["my_needs"] == ["WR"] and r["their_needs"] == ["RB"]
    ]
    assert cross
    assert found.row(0, named=True)["my_fit"] > 50  # a need fit leads the list
    for r in found.iter_rows(named=True):
        assert r["kind"] == "win-win" or min(r["my_fit"], r["their_fit"]) > 0
