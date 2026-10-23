from dataclasses import replace

import polars as pl
import pytest
from test_odds import WEEKS, toy_league

from fantasy.sim import moves
from fantasy.sim.lineup import Player
from fantasy.sim.odds import LeagueData


def league_with(
    extra_players: list[tuple[str, str, float]], boost: dict[str, float] | None = None
) -> LeagueData:
    """The toy league plus unrostered players (id, position, weekly projection)."""
    data = toy_league()
    proj = data.projections
    rows = [(gid, w, value) for gid, _, value in extra_players for w in WEEKS]
    proj = pl.concat([proj, pl.DataFrame(rows, schema=proj.schema, orient="row")])
    for gid, add in (boost or {}).items():
        proj = proj.with_columns(
            pl.when(pl.col("gsis_id") == gid)
            .then(pl.col("projection") + add)
            .otherwise(pl.col("projection"))
            .alias("projection")
        )
    positions = {gid: pos for gid, pos, _ in extra_players}
    return replace(data, projections=proj, positions=positions)


def test_free_agents_are_projected_players_nobody_rosters() -> None:
    data = league_with([("fa_wr", "WR", 15.0)])
    assert moves.free_agents(data) == ["fa_wr"]


def test_a_better_free_agent_adds_points_and_a_worse_one_adds_none() -> None:
    data = league_with([("fa_great", "WR", 18.0), ("fa_scrub", "WR", 3.0)])
    ranked = moves.waiver_candidates(data, roster_id=1)
    by_id = {w.gsis_id: w for w in ranked}
    assert by_id["fa_great"].delta_mu > 0
    assert by_id["fa_scrub"].delta_mu <= 0.0001
    assert ranked[0].gsis_id == "fa_great"
    assert by_id["fa_great"].drop_id.startswith("t1_")  # drops one of my own players


def test_two_for_one_keeps_roster_sizes_and_drops_the_worst_player() -> None:
    data = league_with([("fa_wr", "WR", 5.0)])
    after = moves.apply_trade(data, 1, 2, give=["t1_wr1"], get=["t2_wr1", "t2_te"])
    mine = after.filter(pl.col("roster_id") == 1)["gsis_id"].to_list()
    theirs = after.filter(pl.col("roster_id") == 2)["gsis_id"].to_list()
    assert len(mine) == 6 and len(theirs) == 6
    assert "t2_wr1" in mine and "t1_wr1" not in mine
    assert "t1_wr1" in theirs and "t2_wr1" not in theirs
    # I took two and gave one: the two tight ends tie as the lowest value and the lower id goes
    assert "t2_te" in mine and "t1_te" not in mine


def test_trade_validation() -> None:
    data = league_with([])
    with pytest.raises(ValueError, match="not on your roster"):
        moves.apply_trade(data, 1, 2, give=["t2_wr1"], get=["t2_te"])
    with pytest.raises(ValueError, match="partner's roster"):
        moves.apply_trade(data, 1, 2, give=["t1_wr1"], get=["t1_te"])
    with pytest.raises(ValueError, match="at least one"):
        moves.apply_trade(data, 1, 2, give=[], get=["t2_te"])


def test_getting_the_better_player_helps_me_and_hurts_them() -> None:
    data = league_with([], boost={"t2_rb1": 6.0})
    out = moves.evaluate_trade(data, 1, 2, give=["t1_rb1"], get=["t2_rb1"], n_sims=8000)
    me, them = (
        out.filter(pl.col("side") == "me").row(0, named=True),
        out.filter(pl.col("side") == "them").row(0, named=True),
    )
    assert me["title_after"] > me["title_before"]
    assert them["title_after"] < them["title_before"]
    assert me["wins_after"] > me["wins_before"]


def test_best_swap_never_does_worse_than_dropping_the_lowest_value_player() -> None:
    data = league_with([("fa_wr", "WR", 15.0)])
    ids = moves.team_ids(data, 1)
    base = moves.team_total(data, ids)
    swap = moves.best_swap(data, ids, "fa_wr", base)
    values = moves.ros_value(data, ids)
    lowest = min(ids, key=lambda i: (values[i], i))
    naive = moves.team_total(data, [i for i in ids if i != lowest] + ["fa_wr"]) - base
    assert swap.drop_id in ids
    assert swap.delta_mu >= naive


def test_a_much_better_free_agent_raises_title_odds_and_a_scrub_does_not() -> None:
    data = league_with([("fa_great", "WR", 30.0), ("fa_scrub", "WR", 0.5)])
    ids = moves.team_ids(data, 1)
    base = moves.team_total(data, ids)
    adds = [moves.best_swap(data, ids, c, base) for c in ("fa_great", "fa_scrub")]
    odds = moves.waiver_odds(data, 1, adds, n_sims=8000)
    out = {r["gsis_id"]: r for r in odds.iter_rows(named=True)}
    assert out["fa_great"]["title_delta"] > 0
    assert out["fa_great"]["playoff_delta"] > out["fa_scrub"]["playoff_delta"]
    assert out["fa_scrub"]["title_delta"] <= 0  # a scrub costs the player dropped for him
    assert out["fa_great"]["se_title"] > 0


def test_a_traded_away_starter_leaves_the_week_in_progress() -> None:
    from fantasy.sim import odds

    starters = (Player("t1_wr1", "WR", 13.0), Player("t1_rb1", "RB", 14.0))
    state = odds.CurrentWeek(realized=0.0, open_players=starters, open_k=0, open_def=0)
    data = replace(league_with([]), current={1: state})
    before = odds.build_inputs(data, None, n_sims=50, seed=0)
    after_rosters = moves.apply_trade(data, 1, 2, give=["t1_rb1"], get=["t2_rb1"])
    after = odds.build_inputs(data, after_rosters, n_sims=50, seed=0)  # used to raise KeyError
    assert before.mean[0, 0] == pytest.approx(27.0)
    assert after.mean[0, 0] == pytest.approx(13.0)  # the traded RB's 14 points are gone


def test_trades_are_refused_after_the_deadline() -> None:
    data = replace(league_with([]), current_week=5, trade_deadline=4)
    with pytest.raises(ValueError, match="deadline"):
        moves.evaluate_trade(data, 1, 2, give=["t1_rb1"], get=["t2_rb1"], n_sims=200)


def test_reoptimizing_lets_an_acquired_player_fill_a_traded_starters_slot() -> None:
    from fantasy.sim import odds
    from fantasy.sim.lineup import auto_lineup, lineup_slots

    data = league_with([])
    values = moves.week_values(data)[1]
    positions = moves.position_of(data)
    pool = [Player(i, positions[i], values[i]) for i in moves.team_ids(data, 1)]
    starters = tuple(
        p for p in pool if p.id in auto_lineup(pool, lineup_slots(data.roster_positions)).players
    )
    state = odds.CurrentWeek(realized=0.0, open_players=starters, open_k=0, open_def=0)
    data = replace(data, current={1: state})
    after_rosters = moves.apply_trade(data, 1, 2, give=["t1_rb1"], get=["t2_rb1"])
    kept = odds.build_inputs(data, after_rosters, n_sims=50, seed=0)
    refilled = odds.build_inputs(data, after_rosters, n_sims=50, seed=0, reoptimize=True)
    before = odds.build_inputs(data, None, n_sims=50, seed=0, reoptimize=True)
    assert kept.mean[0, 0] < before.mean[0, 0]  # the lineup set in Sleeper loses the slot
    assert refilled.mean[0, 0] == pytest.approx(before.mean[0, 0])  # an equal RB takes it


def test_finder_refuses_after_the_deadline_and_never_picks_my_own_team() -> None:
    late = replace(league_with([]), current_week=5, trade_deadline=4)
    with pytest.raises(ValueError, match="deadline"):
        moves.find_trades(late, 1)
    found = moves.find_trades(league_with([], boost={"t2_wr1": 8.0}), 1, n_sims=4000)
    assert 1 not in found["partner_id"].to_list()
    for row in found.iter_rows(named=True):
        assert row["my_playoff"] + row["my_title"] > 0
        assert row["their_playoff"] + row["their_title"] > 0


def test_paired_se_is_zero_for_identical_runs_and_below_the_independent_bound() -> None:
    import numpy as np

    rng = np.random.default_rng(0)
    before = rng.random(20000) < 0.2
    assert moves.paired_se(before, before) == 0.0
    after = before.copy()
    after[:200] = ~after[:200]  # a small change made on the same draws
    independent = (0.2 * 0.8 / 20000 * 2) ** 0.5
    assert 0 < moves.paired_se(before, after) < independent
