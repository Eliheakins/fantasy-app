"""The only module the API imports: pure reads over the parquet store.

Optional tables that no stage has written yet come back empty with the right columns. Core
tables (the ones whose emptiness would fabricate defaults) raise FileNotFoundError instead.
The engines live in private sibling modules (`_lineup`, `_market`, `_outlook`, `_engine`) and are
re-exported here. Functions that call `leagues` stay in this module so that a test patching
`data_api.leagues` reaches every caller.
"""

import json
import logging
import math
import warnings
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from fantasy import _digest, _league_view, _season_events, store
from fantasy._engine import _league, _names, _opponent_of, _read, viewed_team
from fantasy._engine import _tier as _tier  # re-exported: tests import it from here
from fantasy._engine import _tier_edges as _tier_edges
from fantasy._lineup import lineup, win_probability
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
from fantasy._schemas import ENGINE_SCHEMAS
from fantasy._scoreboard import SCOREBOARD_SIMS, scoreboard_of
from fantasy._scorecard import Scorecard, scorecard_of
from fantasy._values import market_values as _market_values
from fantasy._values import trade_market as _trade_market
from fantasy._watch import watchlist as _watchlist
from fantasy.config import load_config
from fantasy.sim import moves as moves
from fantasy.sim.availability import kickoffs, missing_kickoffs
from fantasy.sim.depth import position_depth
from fantasy.sim.odds import LeagueData

__all__ = [
    "actions",
    "evaluate_trade",
    "find_trades",
    "freshness",
    "leagues",
    "market_values",
    "trade_market",
    "watchlist",
    "week_calendar",
    "status_changes",
    "lineup",
    "live_score",
    "live_win_row",
    "record_live_tick",
    "game_day",
    "last_week",
    "luck",
    "manager_grades",
    "missing_layers",
    "move_ideas",
    "moves",
    "odds_change",
    "odds_history",
    "ideas_are_mine",
    "player_outlook",
    "player_owners",
    "rostered_unmatched",
    "player_vs_projection",
    "player_points",
    "player_weeks",
    "position_strength",
    "power_rankings",
    "team_grades",
    "refresh_live",
    "roster",
    "schedule",
    "scorecard",
    "scoreboard",
    "scoring_labels",
    "season_events",
    "season_odds",
    "seed_distribution",
    "simulation_behind_inputs",
    "stored_adds",
    "streamers",
    "teams",
    "trade_assets",
    "trade_partners",
    "trade_roster_changes",
    "unmatched",
    "waivers",
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
STREAM_WEEKS = 3
TEAM_COLUMNS = ["roster_id", "team_name", "wins", "losses", "ties", "points_for"]


def scoring_labels(scoring: dict[str, float], roster_positions: list[str]) -> list[str]:
    labels = [f"{scoring.get('rec', 0):g} PPR", f"{scoring.get('pass_td', 0):g}-pt pass TD"]
    if scoring.get("pass_int"):
        labels.append(f"{scoring['pass_int']:g} per INT")
    if "SUPER_FLEX" in roster_positions:
        labels.append("Superflex")
    return labels


def leagues(data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """One row per league with my team, record and scoring labels."""
    mine = _read("league_teams", data_dir).filter(pl.col("is_me"))
    joined = _read("leagues", data_dir).join(mine, on="league_id", how="left")
    labels = [
        ", ".join(scoring_labels(json.loads(scoring), positions))
        for scoring, positions in zip(
            joined["scoring_settings"], joined["roster_positions"], strict=True
        )
    ]
    return joined.with_columns(pl.Series("scoring_labels", labels, dtype=pl.String)).select(
        "league_key",
        "league_id",
        "name",
        "current_week",
        "num_teams",
        "roster_id",
        "team_name",
        "wins",
        "losses",
        "ties",
        "points_for",
        "scoring_labels",
    )


def watchlist(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """My players with a falling snap share or market value, or an injury flag, and why."""
    return _watchlist(league_key, data_dir)


def market_values(
    league_key: str, gsis_ids: list[str], data_dir: Path = store.DATA_DIR
) -> pl.DataFrame:
    """Market values (FantasyCalc) for players in a league's setting; empty without the table."""
    return _market_values(league_key, gsis_ids, data_dir)


def trade_market(
    league_key: str, trades: list[tuple[list[str], list[str]]], data_dir: Path = store.DATA_DIR
) -> list[dict[str, Any] | None]:
    """Per (give_ids, get_ids): market value each side, a hint and the values' date; None for
    every trade when the values table is missing."""
    return _trade_market(league_key, trades, data_dir)


def _my_league(league_key: str, data_dir: Path | None = None) -> dict[str, Any] | None:
    """My row in `leagues` for a league key, or None if it is not there. Looks `leagues` up in
    this module at call time, so a test that patches `data_api.leagues` reaches every caller."""
    rows = (leagues() if data_dir is None else leagues(data_dir)).filter(
        pl.col("league_key") == league_key
    )
    if rows.is_empty():
        return None
    row = rows.row(0, named=True)
    viewed = viewed_team()
    return row if viewed is None else {**row, **_team_fields(row["league_id"], viewed, data_dir)}


def _team_fields(league_id: str, roster_id: int, data_dir: Path | None) -> dict[str, Any]:
    """The `leagues` columns that describe a team, for the team being viewed."""
    team = _read("league_teams", data_dir or store.DATA_DIR).filter(
        (pl.col("league_id") == league_id) & (pl.col("roster_id") == roster_id)
    )
    if team.is_empty():
        raise ValueError(f"unknown team {roster_id} in league {league_id!r}")
    return team.select(TEAM_COLUMNS).row(0, named=True)


def teams(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
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


def roster(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """My roster in a league: starters first, then by position."""
    schema = {c: store.SCHEMAS["sleeper_players"].get(c, pl.Boolean) for c in ROSTER_COLUMNS}
    me = _my_league(league_key, data_dir)
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


def unmatched(data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
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


def season_odds(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Latest simulated playoff and title odds for every team, best title odds first."""
    me = _my_league(league_key, data_dir)
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


def win_needs(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """The viewed team's playoff odds by wins in its next games; empty until simulate has run."""
    me = _my_league(league_key, data_dir)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["win_needs"])
    return _league_view.win_needs(me, data_dir)


def season_events(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Trades, injuries to starters and big weeks of the viewed team, placed on saved runs."""
    me = _my_league(league_key, data_dir)
    if me is None:
        return pl.DataFrame(schema=_season_events.COLUMNS)
    return _season_events.season_events(me, data_dir)


def odds_history(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Every saved simulation run for a league: run_at, team_name, p_playoffs, p_title."""
    me = _my_league(league_key, data_dir)
    columns = ["run_at", "team_name", "roster_id", "p_playoffs", "p_title"]
    if me is None:
        return pl.DataFrame(schema={c: store.SCHEMAS["sim_season_history"][c] for c in columns})
    history = _read("sim_season_history", data_dir, area="archive")
    return history.filter(pl.col("league_id") == me["league_id"]).select(columns)


def power_rankings(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Teams by expected score this week, with season odds and remaining schedule strength."""
    me = _my_league(league_key, data_dir)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["power_rankings"])
    return _league_view.power_rankings(me, data_dir)


def team_grades(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Every team's value over replacement by position, ranked and graded (A to F)."""
    me = _my_league(league_key, data_dir)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["team_grades"])
    data, _ = _league(league_key)
    valuer = moves.Valuer(data)
    strength = moves.position_strength(data, valuer)
    return _league_view.team_grades(me, strength, position_depth(data, valuer), data_dir)


def luck(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Actual wins against the wins the all-play record predicts, luckiest first."""
    me = _my_league(league_key, data_dir)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["luck"])
    return _league_view.luck(me, data_dir)


def manager_grades(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Points started against the best lineup in hindsight, most efficient first."""
    me = _my_league(league_key, data_dir)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["manager_grades"])
    return _league_view.manager_grades(me, data_dir)


def last_week(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """The viewed team's game last week: opponent, points, result, bench points left and luck
    that week. Empty in week 1."""
    me = _my_league(league_key, data_dir)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["last_week"])
    return _digest.last_week(me, data_dir)


def player_vs_projection(
    league_key: str, week: int = 0, data_dir: Path = store.DATA_DIR
) -> pl.DataFrame:
    """Points against the last projection snapshot for the viewed team's skill starters in a week
    (0 is last week), biggest miss first; null projection where no snapshot exists."""
    me = _my_league(league_key, data_dir)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["player_vs_projection"])
    return _digest.player_vs_projection(me, week, data_dir)


def odds_change(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Season odds in the latest run against the last run of an earlier as_of_week; the change
    columns are null when there is none."""
    me = _my_league(league_key, data_dir)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["odds_change"])
    history = _read("sim_season_history", data_dir, area="archive")
    return _digest.odds_change(history, me["league_id"], me["roster_id"])


def move_ideas(league_key: str, kind: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Waiver ("waiver") or trade ("trade") ideas stored by the digest stage, best first. Empty
    when another team is being viewed: the stage stores ideas for my team only."""
    me = _my_league(league_key, data_dir)
    if me is None:
        return pl.DataFrame(schema=store.SCHEMAS["move_ideas"])
    return _digest.move_ideas(me, kind, data_dir)


def ideas_are_mine(league_key: str, data_dir: Path = store.DATA_DIR) -> bool:
    """The viewed team is my own, so stored move ideas apply to it."""
    me = _my_league(league_key, data_dir)
    return me is not None and _digest.is_my_team(me, data_dir)


def stored_adds(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Stored waiver ideas shaped like `waivers`, to pass to `actions(adds=...)`."""
    me = _my_league(league_key, data_dir)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["waivers"])
    return _digest.stored_adds(me, data_dir)


def what_if(league_key: str, week: int = 0, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """My change in playoff and title odds for each outcome of each matchup in a week (0 is the
    current week). Empty for completed and playoff weeks."""
    me = _my_league(league_key, data_dir)
    if me is None:
        return pl.DataFrame(schema=ENGINE_SCHEMAS["what_if"])
    return _league_view.what_if(me, week, data_dir)


def seed_distribution(league_key: str) -> pl.DataFrame:
    """Chance my team finishes each regular-season seed (1 is best): columns seed, p."""
    me = _my_league(league_key)
    if me is None:
        return pl.DataFrame(schema={"seed": pl.Int64, "p": pl.Float64})
    seeds = _read("sim_seeds", store.DATA_DIR, area="derived")
    mine = seeds.filter(
        (pl.col("league_id") == me["league_id"]) & (pl.col("roster_id") == me["roster_id"])
    )
    return mine.select("seed", "p").sort("seed")


def streamers(league_key: str, kind: str, top_n: int = 8) -> pl.DataFrame:
    """Best free K or DEF over the next weeks, plus mine for comparison. kind is "K" or "DEF"."""
    from fantasy.stages.crosswalk import TEAM_MAP

    me = _my_league(league_key)
    if me is None or kind not in ("K", "DEF"):
        return pl.DataFrame(schema=ENGINE_SCHEMAS["streamers"])
    lid, current, mine = me["league_id"], int(me["current_week"]), me["roster_id"]
    proj = (
        _read("streaming_projection", store.DATA_DIR, area="derived")
        .filter((pl.col("league_id") == lid) & (pl.col("kind") == kind))
        .filter(pl.col("week") < current + STREAM_WEEKS)
    )
    rostered = _read("rosters", store.DATA_DIR).filter(pl.col("league_id") == lid)
    players = _read("sleeper_players", store.DATA_DIR).select("sleeper_id", "full_name", "position")
    if kind == "DEF":
        owned = rostered.join(players, on="sleeper_id").filter(pl.col("position") == "DEF")
        owned = owned.with_columns(
            pl.col("sleeper_id")
            .replace_strict(TEAM_MAP, default=pl.col("sleeper_id"))
            .alias("unit")
        )
        name = {u: f"{u} D/ST" for u in proj["unit"].unique()}
    else:
        id_map = _read("id_map", store.DATA_DIR, area="derived").select("sleeper_id", "gsis_id")
        owned = rostered.join(id_map, on="sleeper_id").join(players, on="sleeper_id")
        owned = owned.filter(pl.col("position") == "K").rename({"gsis_id": "unit"})
        name = _names()
    mine_units = set(owned.filter(pl.col("roster_id") == mine)["unit"])
    taken_units = set(owned["unit"]) - mine_units
    totals = proj.group_by("unit", "team").agg(
        pl.col("projection").filter(pl.col("week") == current).sum().alias("this_week"),
        pl.col("projection").sum().alias("next_three"),
    )
    rows = totals.with_columns(
        pl.col("unit").replace_strict(name, default=pl.col("unit")).alias("name"),
        pl.col("unit").is_in(list(mine_units)).alias("is_mine"),
    )
    free = rows.filter(~pl.col("unit").is_in(list(taken_units | mine_units)))
    keep = pl.concat(
        [rows.filter(pl.col("is_mine")), free.sort("next_three", descending=True).head(top_n)]
    )
    return keep.select(*ENGINE_SCHEMAS["streamers"]).sort("next_three", descending=True)


_FRESHNESS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "source": pl.String,
    "updated_at": pl.Datetime("us", "UTC"),
    "age_hours": pl.Float64,
}
UNAVAILABLE = frozenset({"Out", "Doubtful", "IR", "PUP", "Sus", "NFI"})
LINEUP_GAP = 1.0  # expected points below the best lineup before the gap is worth a note
WAIVER_PLAYOFF_GAIN = 0.005  # playoff odds change that makes an add worth mentioning


def actions(
    league_key: str,
    n: int = 3,
    odds: pl.DataFrame | None = None,
    adds: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """The most useful things to do now, most urgent first: kind and text.

    Order: injured or out players in your lineup, a lineup change, then a waiver add. `odds` is a
    `win_probability` result to reuse; `adds` a `waivers`-shaped frame (see `stored_adds`) that
    skips the waiver re-simulation.
    """
    loaded = _league(league_key)
    rows = lineup(league_key, loaded=loaded)
    found: list[tuple[str, str]] = []
    if not rows.is_empty():
        for r in rows.filter(pl.col("starting_now") & ~pl.col("locked")).iter_rows(named=True):
            if r["injury"] in UNAVAILABLE:
                found.append(("Injury", f"{r['full_name']} is {r['injury']} and in your lineup"))
        known = bool(rows["starting_now"].any())
        gap = float(
            rows.filter(pl.col("recommended"))["projection"].to_numpy().sum()
            - rows.filter(pl.col("starting_now"))["projection"].to_numpy().sum()
        )
        by_name = rows["full_name"]
        if known and gap >= LINEUP_GAP:
            start = by_name.filter(rows["recommended"] & ~rows["starting_now"]).to_list()
            sit = by_name.filter(rows["starting_now"] & ~rows["recommended"]).to_list()
            found.append(
                ("Lineup", f"Start {', '.join(start)} over {', '.join(sit)} (+{gap:.1f} points)")
            )
    if odds is None:
        odds = win_probability(league_key, loaded=loaded)
    if not odds.is_empty():
        by_option = {r["option"]: r for r in odds.iter_rows(named=True)}
        pick, best = by_option["win_prob"], by_option["max_points"]
        if pick["tag"] != "same as max points":
            names = dict(zip(rows["gsis_id"], rows["full_name"], strict=True))
            ins = [names[i] for i in set(pick["gsis_ids"]) - set(best["gsis_ids"])]
            out = [names[i] for i in set(best["gsis_ids"]) - set(pick["gsis_ids"])]
            found.append(
                (
                    "Win probability",
                    f"{pick['tag'].capitalize()}: start {', '.join(ins)} over {', '.join(out)} "
                    f"({pick['win_prob']:.1%} vs {best['win_prob']:.1%} to win)",
                )
            )
    if adds is None:
        adds = waivers(league_key, loaded=loaded)
    if not adds.is_empty():
        top = adds.sort("playoff_delta", descending=True).row(0, named=True)
        if top["playoff_delta"] >= WAIVER_PLAYOFF_GAIN:
            found.append(
                (
                    "Waiver",
                    f"Add {top['full_name']}, drop {top['drop_name']}: "
                    f"{top['playoff_delta']:+.1%} playoff odds, {top['delta_points']:+.1f} points",
                )
            )
    return pl.DataFrame(found[:n], schema={"kind": pl.String, "text": pl.String}, orient="row")


FRESHNESS_SOURCES = (
    ("Sleeper", "leagues", "raw"),
    ("NFL stats", "nfl_player_stats", "raw"),
    ("Simulation", "sim_season", "derived"),
)


def freshness(now: datetime | None = None) -> pl.DataFrame:
    """When each data source was last written: source, updated_at (UTC), age_hours."""
    now = now or datetime.now(UTC)
    rows = []
    for label, table, area in FRESHNESS_SOURCES:
        path = store.table_path(table, area)
        if path.exists():
            updated = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            rows.append((label, updated, (now - updated).total_seconds() / 3600))
    return pl.DataFrame(rows, schema=_FRESHNESS_SCHEMA, orient="row")


def simulation_behind_inputs(data_dir: Path = store.DATA_DIR) -> str | None:
    """A note when the simulation table is older than the Sleeper or NFL inputs (a refresh that
    failed part way leaves mixed vintages), else None."""
    sim = store.table_path("sim_season", "derived", data_dir)
    if not sim.exists():
        return None
    inputs = [store.table_path(t, a, data_dir) for _, t, a in FRESHNESS_SOURCES[:2]]
    behind = [p.stem for p in inputs if p.exists() and p.stat().st_mtime > sim.stat().st_mtime]
    if not behind:
        return None
    return f"Season odds are older than {', '.join(behind)}: the last refresh may have failed"


# projection layers that the simulation skips, without error, when their table is missing
OPTIONAL_LAYERS = (
    ("injury model", "injury_effects", "derived"),
    ("outlook", "outlook_effects", "derived"),
    ("matchup and offense effects", "environment_effects", "derived"),
    ("size calibration", "projection_calibration", "derived"),
    ("Sleeper projections", "proj_sleeper", "derived"),
)


def missing_layers(data_dir: Path = store.DATA_DIR) -> list[str]:
    """Names of projection layers the simulation is running without because a stage did not run."""
    config = load_config()
    layers = [
        layer
        for layer in OPTIONAL_LAYERS
        if config.environment_layer or layer[1] != "environment_effects"
    ]
    if config.projection_model == "learned":
        layers.append(("learned projections", "proj_learned", "derived"))
    missing = [
        label
        for label, table, area in layers
        if not store.table_path(table, area, data_dir).exists()
    ]
    # prop_points writes these for the current week only, so an empty table is a missing source
    labels = {"fftoday": "FFToday projections", "props": "prop lines"}
    for source in [s for s in config.blend_sources if s in labels]:
        table = "proj_props" if source == "props" else "proj_outside"
        path = store.table_path(table, "derived", data_dir)
        rows = pl.scan_parquet(path) if path.exists() else None
        if rows is not None and source != "props":
            rows = rows.filter(pl.col("source") == source)
        if rows is None or rows.select(pl.len()).collect().item() == 0:
            missing.append(labels[source])
    return missing


def refresh_live() -> int:
    """Pull this week's matchups from Sleeper again so scores are current. Returns player rows."""
    from fantasy.stages.sync_sleeper import sync_week

    week = int(leagues()["current_week"].to_numpy().max())
    return sync_week(week)


LIVE_HISTORY = "live_win_history"
log = logging.getLogger(__name__)


def _open_starters(data: LeagueData, roster_id: int) -> int:
    """Set starters still to score: players plus K and DEF slots (a game under way counts whole)."""
    state = data.current[roster_id]
    return len(state.open_players) + math.ceil(state.open_k) + math.ceil(state.open_def)


def live_win_row(league_key: str) -> dict[str, Any] | None:
    """My matchup now (the viewed team's with ?team=): chance to win, points so far, projected
    finals and starters left. Display only, read from the scoreboard and live_score. None when the
    week has no matchup for the team."""
    data, mine = _league(league_key)
    opp = _opponent_of(data, mine, data.current_week)
    board = scoreboard_of(data, mine)
    if opp is None or board.is_empty() or mine not in data.current or opp not in data.current:
        return None
    first = board.row(0, named=True)
    side = "a" if first["a_is_me"] else "b"
    score = {r["side"]: r for r in live_score(league_key).iter_rows(named=True)}
    if "me" not in score or "them" not in score:
        return None
    return {
        "league_id": data.league_id,
        "week": data.current_week,
        "roster_id": mine,
        "my_team": score["me"]["team_name"],
        "opp_team": score["them"]["team_name"],
        "win_prob": first[f"{side}_win_prob"],
        "my_points": score["me"]["points"],
        "opp_points": score["them"]["points"],
        "my_projected": score["me"]["projected_final"],
        "opp_projected": score["them"]["projected_final"],
        "my_left": _open_starters(data, mine),
        "opp_left": _open_starters(data, opp),
    }


def record_live_tick(now: datetime | None = None) -> None:
    """Append my matchup of each league to live_win_history in one write, once per run_at,
    current week only (a league's older rows go). Called by the live refresh and the Refresh
    scores button, never touches sim_season_history. Any failure is logged and swallowed:
    display-only history must not fail a refresh."""
    try:
        run_at = (now or datetime.now(UTC)).isoformat(timespec="seconds")
        found = []
        for league_key in leagues()["league_key"].to_list():
            try:
                row = live_win_row(league_key)
            except Exception:  # noqa: BLE001 - one league failing must not stop the other
                log.exception("live history failed for %s", league_key)
                continue
            if row is not None:
                found.append({**row, "run_at": run_at})
        if found:
            _append_live_rows(found)
    except Exception:  # noqa: BLE001
        log.exception("live history failed")


def _append_live_rows(rows: list[dict[str, Any]]) -> None:
    schema = store.SCHEMAS[LIVE_HISTORY]
    new = pl.DataFrame([{c: r[c] for c in schema} for r in rows], schema=schema).unique(
        subset=["league_id", "roster_id", "run_at"], keep="last", maintain_order=True
    )
    try:
        old = store.read_table(LIVE_HISTORY, "derived", store.DATA_DIR)
    except FileNotFoundError:
        old = new.clear()
    for league_id, week in {(r["league_id"], r["week"]) for r in rows}:
        old = old.filter(~((pl.col("league_id") == league_id) & (pl.col("week") != week)))
    old = old.join(
        new.select("league_id", "roster_id", "run_at"),
        how="anti",
        on=["league_id", "roster_id", "run_at"],
    )
    store.write_table(LIVE_HISTORY, pl.concat([old, new]), "derived", store.DATA_DIR)


def game_day(league_key: str) -> dict[str, Any]:
    """The numbers now plus today's history for my team (the viewed team with ?team=).
    `as_of` is when `current` was computed: the chart adds it as the last point, so the line
    and the headline number agree (the win probability is seeded, so it only moves with the data
    and the game clock)."""
    current = live_win_row(league_key)
    if current is None:
        return {"week": None, "as_of": None, "current": None, "history": []}
    try:
        table = store.read_table(LIVE_HISTORY, "derived", store.DATA_DIR)
    except FileNotFoundError:
        table = pl.DataFrame(schema=store.SCHEMAS[LIVE_HISTORY])
    mine = table.filter(
        (pl.col("league_id") == current["league_id"])
        & (pl.col("roster_id") == current["roster_id"])
        & (pl.col("week") == current["week"])
    ).sort("run_at")
    shown = {**current, "points_needed": current["opp_projected"] - current["my_points"]}
    return {
        "week": current["week"],
        "as_of": datetime.now(UTC).isoformat(timespec="seconds"),
        "current": shown,
        "history": mine.to_dicts(),
    }


def scoreboard(league_key: str, week: int = 0, n_sims: int = SCOREBOARD_SIMS) -> pl.DataFrame:
    """Every matchup of a week with projected totals, ranges and chances to win, my matchup
    first (see `_scoreboard`). `is_me` follows the viewed team."""
    data, mine = _league(league_key)
    return scoreboard_of(data, mine, week, n_sims)


def scorecard(league_key: str, data_dir: Path = store.DATA_DIR) -> Scorecard:
    """Our archived pre-kickoff projections scored against actual points (see `_scorecard`)."""
    me = _my_league(league_key, data_dir)
    if me is None:
        raise ValueError(f"unknown league {league_key!r}")
    return scorecard_of(me["league_id"], data_dir)


def _waiver_day(settings_json: str | None) -> tuple[int | None, bool]:
    """Sleeper's waiver clear day (0 is Monday) and whether waivers run daily instead."""
    try:
        settings = json.loads(settings_json) if settings_json else {}
    except json.JSONDecodeError:
        return None, False  # unreadable settings: this league gets no waiver day
    if not isinstance(settings, dict):
        return None, False
    if settings.get("daily_waivers"):
        return None, True  # daily waivers have no single clear day
    day = settings.get("waiver_day_of_week")
    return (day if isinstance(day, int) else None), False


def week_calendar(data_dir: Path = store.DATA_DIR) -> dict[str, Any]:
    """The current NFL week, each team's kickoff (US Eastern) and each league's waiver clear day.
    The week is the highest current week over my leagues, as the live refresh reads it."""
    current = leagues(data_dir)
    weeks = current["current_week"].drop_nulls()
    week = int(weeks.max()) if len(weeks) else None  # type: ignore[arg-type]
    games: dict[str, datetime] = {}
    unknown: set[str] = set()
    if week is not None:
        schedules, season = _read("nfl_schedules", data_dir), load_config().season
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")  # teams with no kickoff time are reported below
            games = kickoffs(schedules, season, week)
        unknown = missing_kickoffs(schedules, season, week) - set(games)
    raw = _read("leagues", data_dir)
    settings = dict(raw.select("league_key", "settings").iter_rows()) if "settings" in raw else {}
    waivers = []
    for league_key, name in current.select("league_key", "name").iter_rows():
        day, daily = _waiver_day(settings.get(league_key))
        waivers.append({"league_key": league_key, "name": name, "day_of_week": day, "daily": daily})
    return {
        "week": week,
        "kickoffs": [{"team": t, "kickoff": k.isoformat()} for t, k in sorted(games.items())]
        + [{"team": t, "kickoff": None} for t in sorted(unknown)],
        "waivers": waivers,
    }


def _as_utc(iso: str) -> datetime:
    parsed = datetime.fromisoformat(iso)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def status_changes(
    league_key: str, since: datetime, data_dir: Path = store.DATA_DIR
) -> pl.DataFrame:
    """My players whose injury status differs between the last daily Sleeper snapshot at or before
    `since` and the latest one. Empty when no snapshot is that old or none is newer."""
    me = _my_league(league_key, data_dir)
    if me is None:
        raise ValueError(f"unknown league {league_key!r}")
    if since.tzinfo is None:
        since = since.replace(tzinfo=UTC)  # a time with no zone is read as UTC
    columns = ["sleeper_id", "full_name", "position", "team", "before", "after"]
    empty = pl.DataFrame(schema={c: pl.String for c in columns})
    snaps = _read("sleeper_player_status", data_dir, area="archive")
    stamps = {t: _as_utc(t) for t in snaps["fetched_at"].drop_nulls().unique()}
    old = [t for t, at in stamps.items() if at <= since]
    if not old:
        return empty
    before_at, after_at = max(old, key=stamps.__getitem__), max(stamps, key=stamps.__getitem__)
    if before_at == after_at:
        return empty

    def pick(at: str, name: str) -> pl.DataFrame:
        return snaps.filter(pl.col("fetched_at") == at).select(
            "sleeper_id", pl.col("injury_status").alias(name)
        )

    mine = _read("rosters", data_dir).filter(
        (pl.col("league_id") == me["league_id"]) & (pl.col("roster_id") == me["roster_id"])
    )
    players = _read("sleeper_players", data_dir).select(
        "sleeper_id", "full_name", "position", "team"
    )
    return (
        mine.select("sleeper_id")
        .join(pick(before_at, "before"), on="sleeper_id", how="left")
        .join(pick(after_at, "after"), on="sleeper_id", how="left")
        .filter(pl.col("before").ne_missing(pl.col("after")))
        .join(players, on="sleeper_id", how="left")
        .select(columns)
        .sort("full_name", "sleeper_id")
    )
