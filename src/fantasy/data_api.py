"""The read facade the API imports: pure reads over the parquet store.

Optional tables that no stage has written yet come back empty with the right columns. Core
tables (the ones whose emptiness would fabricate defaults) raise FileNotFoundError instead.
The engines live in package-internal sibling modules (`_lineup`, `_market`, `_outlook`, `_engine`,
`_leagues`, `_live` (the one that writes), `_status`, `_calendar`, `_actions`) and are re-exported
here. Nothing on this path imports `fantasy.stages` at import time (a test pins it).

Every read takes `data_dir` (None: the project data folder, looked up at call time). Functions
about "my team" also take `team`, a roster id that stands in for my team (None: the Sleeper
is_me team). The API passes both from its request context.
"""

from pathlib import Path
from typing import Any

import polars as pl

from fantasy import _digest, _league_view, _season_events, store
from fantasy._actions import actions as actions
from fantasy._actions import streamers as streamers
from fantasy._calendar import status_changes as status_changes
from fantasy._calendar import week_calendar as week_calendar
from fantasy._engine import _clear_league_cache as clear_league_cache
from fantasy._engine import _league, _read
from fantasy._engine import _tier as _tier  # re-exported: tests import it from here
from fantasy._engine import _tier_edges as _tier_edges
from fantasy._engine import data_version as data_version
from fantasy._engine import file_stamp as file_stamp
from fantasy._engine import pinned_version as pinned_version
from fantasy._leagues import TEAM_COLUMNS, leagues, my_league, scoring_labels
from fantasy._lineup import lineup, win_probability
from fantasy._live import game_day, live_win_row, record_live_tick, refresh_live
from fantasy._market import (
    evaluate_trade,
    find_trades,
    player_points,
    player_weeks,
    position_strength,
    trade_assets,
    trade_partners,
    trade_roster_changes,
    waivers,
)
from fantasy._outlook import live_score, player_outlook, player_owners, rostered_unmatched, schedule
from fantasy._profile import player_profile
from fantasy._schemas import ENGINE_SCHEMAS
from fantasy._scoreboard import SCOREBOARD_SIMS, scoreboard_of
from fantasy._scorecard import Scorecard, scorecard_of
from fantasy._status import freshness, missing_layers, refresh_runs, simulation_behind_inputs
from fantasy._values import market_values as _market_values
from fantasy._values import trade_market as _trade_market
from fantasy._watch import watchlist as _watchlist
from fantasy.sim import moves as moves
from fantasy.sim.depth import position_depth

__all__ = [
    "actions",
    "clear_league_cache",
    "data_version",
    "evaluate_trade",
    "file_stamp",
    "find_trades",
    "freshness",
    "game_day",
    "ideas_are_mine",
    "last_week",
    "leagues",
    "lineup",
    "live_score",
    "live_win_row",
    "luck",
    "manager_grades",
    "market_values",
    "missing_layers",
    "move_ideas",
    "moves",
    "odds_change",
    "odds_history",
    "pinned_version",
    "player_outlook",
    "player_owners",
    "player_points",
    "player_profile",
    "player_vs_projection",
    "player_weeks",
    "position_strength",
    "power_rankings",
    "record_live_tick",
    "refresh_live",
    "refresh_runs",
    "roster",
    "rostered_unmatched",
    "schedule",
    "scoreboard",
    "scorecard",
    "scoring_labels",
    "season_events",
    "season_odds",
    "seed_distribution",
    "simulation_behind_inputs",
    "status_changes",
    "stored_adds",
    "streamers",
    "team_grades",
    "teams",
    "trade_assets",
    "trade_market",
    "trade_partners",
    "trade_roster_changes",
    "unmatched",
    "waivers",
    "watchlist",
    "week_calendar",
    "what_if",
    "win_needs",
    "win_probability",
]

POSITION_ORDER = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "K": 4, "DEF": 5}
ROSTER_COLUMNS = [
    "sleeper_id",
    "full_name",
    "position",
    "team",
    "injury_status",
    "is_starter",
    "is_ir",
]


def watchlist(
    league_key: str, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """My players with a falling snap share or market value, or an injury flag, and why."""
    return _watchlist(league_key, data_dir, team)


def market_values(
    league_key: str, gsis_ids: list[str], data_dir: Path | None = None
) -> pl.DataFrame:
    """Market values (FantasyCalc) for players in a league's setting; empty without the table."""
    return _market_values(league_key, gsis_ids, data_dir)


def trade_market(
    league_key: str, trades: list[tuple[list[str], list[str]]], data_dir: Path | None = None
) -> list[dict[str, Any] | None]:
    """Per (give_ids, get_ids): market value each side, a hint and the values' date; None for
    every trade when the values table is missing."""
    return _trade_market(league_key, trades, data_dir)


def teams(league_key: str, data_dir: Path | None = None) -> pl.DataFrame:
    """Every team in a league, for the team selector: id, name, record, and which one is me."""
    league = leagues(data_dir).filter(pl.col("league_key") == league_key)
    if league.is_empty():
        raise ValueError(f"unknown league {league_key!r}")
    return (
        _read("league_teams", data_dir)
        .filter(pl.col("league_id") == league["league_id"][0])
        .select(*TEAM_COLUMNS, "is_me")
        .sort("roster_id")
    )


def roster(league_key: str, data_dir: Path | None = None, team: int | None = None) -> pl.DataFrame:
    """My roster in a league: starters first, then by position."""
    schema = {c: store.SCHEMAS["sleeper_players"].get(c, pl.Boolean) for c in ROSTER_COLUMNS}
    me = my_league(league_key, data_dir, team)
    if me is None:
        return pl.DataFrame(schema=schema)
    mine = _read("rosters", data_dir).filter(
        (pl.col("league_id") == me["league_id"]) & (pl.col("roster_id") == me["roster_id"])
    )
    players = _read("sleeper_players", data_dir).select(
        "sleeper_id", "full_name", "position", "team", "injury_status"
    )
    order = pl.col("position").replace_strict(POSITION_ORDER, default=len(POSITION_ORDER))
    return (
        mine.join(players, on="sleeper_id", how="left")
        .sort(["is_starter", order, "full_name"], descending=[True, False, False])
        .select(ROSTER_COLUMNS)
    )


def unmatched(data_dir: Path | None = None) -> pl.DataFrame:
    """Active non-DEF players with no nflverse ID (shown as "no history")."""
    id_map = _read("id_map", data_dir, area="derived").select("sleeper_id", "gsis_id")
    return (
        _read("sleeper_players", data_dir)
        .filter((pl.col("status") == "Active") & pl.col("team").is_not_null())
        .filter(pl.col("position") != "DEF")
        .select("sleeper_id", "full_name", "position", "team")
        .join(id_map, on="sleeper_id", how="left")
        .filter(pl.col("gsis_id").is_null())
        .select("sleeper_id", "full_name", "position", "team")
        .sort("position", "full_name")
    )


def season_odds(
    league_key: str, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """Latest simulated playoff and title odds for every team, best title odds first."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["season_odds"])
    odds = _read("sim_season", data_dir, area="derived").filter(
        pl.col("league_id") == me["league_id"]
    )
    return (
        odds.with_columns((pl.col("roster_id") == me["roster_id"]).alias("is_me"))
        .select(*ENGINE_SCHEMAS["season_odds"])
        .sort("p_title", descending=True)
    )


def win_needs(
    league_key: str, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """The viewed team's playoff odds by wins in its next games; empty until simulate has run."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["win_needs"])
    return _league_view.win_needs(me, data_dir)


def season_events(
    league_key: str, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """Trades, injuries to starters and big weeks of the viewed team, placed on saved runs."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        return pl.DataFrame(schema=_season_events.COLUMNS)
    return _season_events.season_events(me, data_dir)


def odds_history(
    league_key: str, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """Every saved simulation run for a league: run_at, its week, team_name, p_playoffs, p_title."""
    me = my_league(league_key, data_dir, team)
    columns = ["run_at", "team_name", "roster_id", "p_playoffs", "p_title", "as_of_week"]
    if me is None:
        return pl.DataFrame(schema={c: store.SCHEMAS["sim_season_history"][c] for c in columns})
    history = _read("sim_season_history", data_dir, area="archive")
    return history.filter(pl.col("league_id") == me["league_id"]).select(columns)


def power_rankings(
    league_key: str, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """Teams by expected score this week, with season odds and remaining schedule strength."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["power_rankings"])
    return _league_view.power_rankings(me, data_dir)


def team_grades(
    league_key: str, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """Every team's value over replacement by position, ranked and graded (A to F)."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["team_grades"])
    data, _ = _league(league_key, data_dir, team)
    valuer = moves.Valuer(data)
    strength = moves.position_strength(data, valuer)
    return _league_view.team_grades(me, strength, position_depth(data, valuer), data_dir)


def luck(league_key: str, data_dir: Path | None = None, team: int | None = None) -> pl.DataFrame:
    """Actual wins against the wins the all-play record predicts, luckiest first."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["luck"])
    return _league_view.luck(me, data_dir)


def manager_grades(
    league_key: str, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """Points started against the best lineup in hindsight, most efficient first."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["manager_grades"])
    return _league_view.manager_grades(me, data_dir)


def last_week(
    league_key: str, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """The viewed team's game last week: opponent, points, result, bench points left and luck
    that week. Empty in week 1."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["last_week"])
    return _digest.last_week(me, data_dir)


def player_vs_projection(
    league_key: str, week: int = 0, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """Points against the last projection snapshot for the viewed team's skill starters in a week
    (0 is last week), biggest miss first; null projection where no snapshot exists."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["player_vs_projection"])
    return _digest.player_vs_projection(me, week, data_dir)


def odds_change(
    league_key: str, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """Season odds in the latest run against the last run of an earlier as_of_week; the change
    columns are null when there is none."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["odds_change"])
    history = _read("sim_season_history", data_dir, area="archive")
    return _digest.odds_change(history, me["league_id"], me["roster_id"])


def move_ideas(
    league_key: str, kind: str, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """Waiver ("waiver") or trade ("trade") ideas stored by the digest stage, best first. Empty
    when another team is being viewed: the stage stores ideas for my team only."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        return pl.DataFrame(schema=store.SCHEMAS["move_ideas"])
    return _digest.move_ideas(me, kind, data_dir)


def ideas_are_mine(league_key: str, data_dir: Path | None = None, team: int | None = None) -> bool:
    """The viewed team is my own, so stored move ideas apply to it."""
    me = my_league(league_key, data_dir, team)
    return me is not None and _digest.is_my_team(me, data_dir)


def stored_adds(
    league_key: str, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """Stored waiver ideas shaped like `waivers`, to pass to `actions(adds=...)`."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["waivers"])
    return _digest.stored_adds(me, data_dir)


def what_if(
    league_key: str, week: int = 0, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """My change in playoff and title odds for each outcome of each matchup in a week (0 is the
    current week). Empty for completed and playoff weeks."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["what_if"])
    return _league_view.what_if(me, week, data_dir)


def seed_distribution(
    league_key: str, data_dir: Path | None = None, team: int | None = None
) -> pl.DataFrame:
    """Chance my team finishes each regular-season seed (1 is best): columns seed, p."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        return pl.DataFrame(schema={"seed": pl.Int64, "p": pl.Float64})
    seeds = _read("sim_seeds", data_dir, area="derived")
    mine = seeds.filter(
        (pl.col("league_id") == me["league_id"]) & (pl.col("roster_id") == me["roster_id"])
    )
    return mine.select("seed", "p").sort("seed")


def scoreboard(
    league_key: str,
    week: int = 0,
    n_sims: int = SCOREBOARD_SIMS,
    data_dir: Path | None = None,
    team: int | None = None,
) -> pl.DataFrame:
    """Every matchup of a week with projected totals, ranges and chances to win, my matchup
    first (see `_scoreboard`). `is_me` follows the viewed team."""
    data, mine = _league(league_key, data_dir, team)
    return scoreboard_of(data, mine, week, n_sims, data_dir)


def scorecard(league_key: str, data_dir: Path | None = None, team: int | None = None) -> Scorecard:
    """Our archived pre-kickoff projections scored against actual points (see `_scorecard`)."""
    me = my_league(league_key, data_dir, team)
    if me is None:
        raise ValueError(f"unknown league {league_key!r}")
    return scorecard_of(me["league_id"], data_dir)
