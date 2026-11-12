from dataclasses import replace

import polars as pl
import pytest
from test_moves import league_with
from test_odds import toy_league

from fantasy.sim import moves
from fantasy.sim.horizon import horizon_weeks
from fantasy.sim.odds import HAZARD, STAY_OUT, LeagueData
from fantasy.sim.roster import Valuer, ros_value
from fantasy.sim.value import absence_probs
from fantasy.sim.waivers import best_swap, waiver_candidates

WEEKS = range(1, 11)  # the toy league: playoffs start in week 8 and last 3 weeks


def injured_te_league() -> LeagueData:
    """One team of a TE starter out in week 1 (chain after) and a TE backup; one TE slot."""
    rows = [(w, "s", 10.0, 0.0 if w == 1 else 1.0) for w in WEEKS]
    rows += [(w, "b", 5.0, 1.0) for w in WEEKS]
    proj = pl.DataFrame(rows, schema=["week", "gsis_id", "projection", "play_prob"], orient="row")
    rosters = pl.DataFrame(
        [(1, "s", "TE"), (1, "b", "TE")], schema=["roster_id", "gsis_id", "position"], orient="row"
    )
    return replace(toy_league(), roster_positions=["TE"], rosters=rosters, projections=proj)


def week_total(chance: float) -> float:
    return 10.0 - chance * 5.0  # starter 10, backup 5, no free agents


def test_no_weeks_equals_the_full_season_value() -> None:
    data = injured_te_league()
    chances = absence_probs((0.0,), 10, HAZARD, STAY_OUT)
    expected = sum(week_total(q) for q in chances)
    assert Valuer(data)(["s", "b"]) == pytest.approx(expected)
    assert Valuer(data, weeks=None)(["s", "b"]) == Valuer(data)(["s", "b"])
    assert Valuer(data, weeks=set(WEEKS))(["s", "b"]) == pytest.approx(expected)


def test_horizon_value_uses_absence_chances_at_each_weeks_true_offset() -> None:
    data = injured_te_league()
    chances = absence_probs((0.0,), 10, HAZARD, STAY_OUT)
    expected = sum(week_total(chances[w - 1]) for w in (8, 9, 10))
    assert Valuer(data, weeks={8, 9, 10})(["s", "b"]) == pytest.approx(expected)
    # filtering the projections first would read week 8 as the next week: a bigger absence
    assert chances[7] < chances[0]


def test_horizon_value_is_the_full_value_minus_the_skipped_weeks() -> None:
    data = injured_te_league()
    ids = ["s", "b"]
    full = Valuer(data)(ids)
    assert Valuer(data, weeks={8, 9, 10})(ids) + Valuer(data, weeks=range(1, 8))(ids) == (
        pytest.approx(full)
    )


def test_ros_value_sums_only_the_given_weeks() -> None:
    data = injured_te_league()
    assert ros_value(data, ["b"], weeks={8, 9, 10}) == {"b": 15.0}
    assert ros_value(data, ["b"]) == {"b": 50.0}
    assert ros_value(data, ["b"], weeks=set()) == {"b": 0.0}


@pytest.mark.parametrize(
    ("teams", "round_type", "last"),
    [(4, 0, 16), (4, 1, 17), (4, 2, 18), (6, 0, 17), (6, 1, 18), (6, 2, 20), (8, 0, 17)],
)
def test_playoff_horizon_runs_from_the_start_through_the_last_bracket_week(
    teams: int, round_type: int, last: int
) -> None:
    data = replace(toy_league(), current_week=10, playoff_start=15)
    data = replace(data, playoff_teams=teams, round_type=round_type)
    assert horizon_weeks(data, "playoffs") == tuple(range(15, last + 1))


def test_playoff_horizon_drops_weeks_already_played_and_is_empty_after_the_final() -> None:
    base = replace(toy_league(), playoff_start=15, playoff_teams=6, round_type=0)
    assert horizon_weeks(replace(base, current_week=16), "playoffs") == (16, 17)
    assert horizon_weeks(replace(base, current_week=18), "playoffs") == ()


def test_ros_horizon_is_every_projected_week_from_the_current_one() -> None:
    data = replace(toy_league(), current_week=4)
    assert horizon_weeks(data, "ros") == (4, 5, 6, 7, 8, 9, 10)
    assert horizon_weeks(replace(data, current_week=12), "ros") == ()


def test_waivers_by_playoff_weeks_rank_a_late_player_above_an_early_one() -> None:
    data = league_with([("early", "WR", 30.0), ("late", "WR", 30.0)])
    proj = data.projections.filter(
        ~(
            ((pl.col("gsis_id") == "early") & (pl.col("week") >= 8))
            | ((pl.col("gsis_id") == "late") & (pl.col("week") < 8))
        )
    )
    data = replace(data, projections=proj)
    weeks = horizon_weeks(data, "playoffs")
    assert weeks == (8, 9, 10)
    ros = [w.gsis_id for w in waiver_candidates(data, 1, top_n=2)]
    late = [w.gsis_id for w in waiver_candidates(data, 1, top_n=2, weeks=weeks)]
    assert ros[0] == "early"
    assert late[0] == "late"
    ids = moves.team_ids(data, 1)
    valuer = Valuer(data, weeks=weeks)
    swap = best_swap(data, ids, "late", valuer(ids), valuer, weeks=weeks)
    assert swap.gsis_id == "late" and swap.delta_mu > 0
