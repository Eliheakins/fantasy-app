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
