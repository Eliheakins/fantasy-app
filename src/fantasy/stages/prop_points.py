"""The current week's prop-implied and FFToday points per league, for the blend in simulate.

proj_props: for each of this week's games, the latest Odds API snapshot under data/archive/odds
taken before its kickoff, used only if it is at most MAX_LINE_AGE_HOURS old then. Method of
research/props_check.py: de-vig each book's two-way prices; a yardage line L is a median, mean =
r_m * (L + z * sigma_m) with z = Phi^-1(p_over) clamped to +/-Z_CLAMP; receptions by Poisson
inversion, mean = r_m * lambda; books averaged. X (non-TD points) = league weights times those
means, the player's lagged mean for a stat without a line. Points = X + his lagged mean of every
other point (touchdowns, interceptions, fumbles, two-point conversions). Only `prop_positions`
(RB and WR) with every line of PRIMARY and at least one earlier game. 2024 held out: the equal
blend with the learned projection cut RMSE 1.6% and 1.4% (docs/decisions.md).

proj_outside: each outside source's latest snapshot per position of the current week
(outside_projections) fetched since the Tuesday before the week's first kickoff, scored under the
league's rules plus the player's lagged mean of fumble-lost and two-point points under that
league's weights (FFToday projects neither), less FFToday's 2025 mean error by position
(FFTODAY_BIAS).

No network. No snapshot or a stale one, or any failure in the props half, leaves proj_props empty
with a log line; a source's age and missing positions are logged.
Run: uv run python -m fantasy.stages.prop_points
"""

import calendar
import json
import math
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import NormalDist
from typing import Any

import polars as pl
from scipy.optimize import brentq
from scipy.special import gammaincc

from fantasy import store
from fantasy.config import load_config
from fantasy.sim.availability import EASTERN
from fantasy.stages import outside_projections as op
from fantasy.stages.crosswalk import norm_team, normalize_name
from fantasy.stages.sleeper_projections import score_stats
from fantasy.stages.snapshot_odds import ODDS_DIR

Z_CLAMP = 1.0
LAG_GAMES = 8
# lines older than this at their game's kickoff are dropped; a Sunday 11:45 ET slate pull is
# 32.5 hours before Monday night's kickoff
MAX_LINE_AGE_HOURS = 36
STAMP = re.compile(r"\d{8}T\d{6}Z")  # a finished snapshot folder (snapshot_odds)
# market -> (nflverse stat, Sleeper scoring key)
MARKETS = {
    "player_pass_yds": ("passing_yards", "pass_yd"),
    "player_rush_yds": ("rushing_yards", "rush_yd"),
    "player_receptions": ("receptions", "rec"),
    "player_reception_yds": ("receiving_yards", "rec_yd"),
}
# (r_m, sigma_m): research/prop_constants.py on the free archive's 2024-2025 FanDuel lines
PROP_FIT = {
    "player_pass_yds": (1.0010, 71.15),
    "player_rush_yds": (1.0962, 27.30),
    "player_receptions": (0.9861, 0.0),
    "player_reception_yds": (1.1594, 27.60),
}
# lines a player needs before his prop points are used
PRIMARY = {
    "QB": ("player_pass_yds",),
    "RB": ("player_rush_yds",),
    "WR": ("player_receptions", "player_reception_yds"),
    "TE": ("player_receptions", "player_reception_yds"),
}
# FFToday's mean error by position (projection after the lagged fumble and two-point points
# minus actual): research/fftoday_bias.py, 2025 weeks 1 to 6, mean of the two leagues. On 2026
# weeks 1 to 6 the corrected mean with ours was no worse at any position (pooled RMSE -0.005)
FFTODAY_BIAS = {"QB": -0.59, "RB": -0.44, "WR": 1.16, "TE": 0.08}
# Sleeper key -> nflverse columns of the points FFToday leaves out
UNPROJECTED = {
    "fum_lost": ("sack_fumbles_lost", "rushing_fumbles_lost", "receiving_fumbles_lost"),
    "pass_2pt": ("passing_2pt_conversions",),
    "rush_2pt": ("rushing_2pt_conversions",),
    "rec_2pt": ("receiving_2pt_conversions",),
}
TEAM_NAMES = {
    "Arizona Cardinals": "ARI",
    "Atlanta Falcons": "ATL",
    "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF",
    "Carolina Panthers": "CAR",
    "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LA",
    "Miami Dolphins": "MIA",
    "Minnesota Vikings": "MIN",
    "New England Patriots": "NE",
    "New Orleans Saints": "NO",
    "New York Giants": "NYG",
    "New York Jets": "NYJ",
    "Philadelphia Eagles": "PHI",
    "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA",
    "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN",
    "Washington Commanders": "WAS",
}
LINE_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "stamp": pl.Datetime("us", "UTC"),
    "event_id": pl.String,
    "kickoff": pl.Datetime("us", "UTC"),
    "home": pl.String,
    "away": pl.String,
    "book": pl.String,
    "market": pl.String,
    "player": pl.String,
    "line": pl.Float64,
    "p_over": pl.Float64,
}


def implied(price: float) -> float:
    """Implied probability of an American price."""
    return -price / (-price + 100) if price < 0 else 100 / (price + 100)


def poisson_lambda(line: float, p_over: float) -> float:
    """lambda with P(X > line) = p_over: P(X > line) = 1 - P(X <= floor(line)) and
    P(X <= k - 1) = Q(k, lambda), so k = floor(line) + 1 (also right for an integer line)."""
    k = math.floor(line) + 1
    return float(brentq(lambda lam: gammaincc(k, lam) - (1 - p_over), 1e-6, 60.0))


def prop_mean(market: str, line: float, p_over: float) -> float:
    r, sigma = PROP_FIT[market]
    if market == "player_receptions":
        return r * poisson_lambda(line, p_over)
    z = min(max(NormalDist().inv_cdf(p_over), -Z_CLAMP), Z_CLAMP)
    return r * (line + z * sigma)


def event_lines(event: dict[str, Any], stamp: datetime) -> list[dict[str, Any]]:
    """One row per book, market and player with an Over and an Under at the same line."""
    head = {
        "stamp": stamp,
        "event_id": event["id"],
        "kickoff": datetime.fromisoformat(event["commence_time"]),
        "home": TEAM_NAMES.get(event["home_team"]),
        "away": TEAM_NAMES.get(event["away_team"]),
    }
    rows = []
    for book in event.get("bookmakers", []):
        for market in book.get("markets", []):
            if market["key"] not in MARKETS:
                continue
            price = {
                (o.get("description"), o.get("point"), o["name"]): o["price"]
                for o in market["outcomes"]
            }
            for (player, point, side), over in price.items():
                under = price.get((player, point, "Under"))
                if side != "Over" or under is None or point is None:
                    continue
                q_over, q_under = implied(over), implied(under)
                rows.append(
                    {
                        **head,
                        "book": book["key"],
                        "market": market["key"],
                        "player": player,
                        "line": float(point),
                        "p_over": q_over / (q_over + q_under),
                    }
                )
    return rows


def read_snapshots(odds_dir: Path = ODDS_DIR) -> pl.DataFrame:
    """Every line in every finished snapshot folder."""
    rows: list[dict[str, Any]] = []
    folders = sorted(odds_dir.iterdir()) if odds_dir.is_dir() else []
    for folder in folders:
        if not (folder.is_dir() and STAMP.fullmatch(folder.name)):
            continue
        stamp = datetime.strptime(folder.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        for file in sorted(folder.glob("*.json")):
            try:
                rows += event_lines(json.loads(file.read_text()), stamp)
            except (ValueError, KeyError, TypeError) as err:  # one bad file skips one game
                print(f"warning: odds file {file} skipped: {err!r}")
    return pl.DataFrame(rows, schema=LINE_SCHEMA)


def week_lines(lines: pl.DataFrame, schedule: pl.DataFrame) -> pl.DataFrame:
    """The week's games (`schedule`: one week's rows; games without a date are left out), each
    from its latest snapshot before kickoff if that is at most MAX_LINE_AGE_HOURS old: home, away,
    player, market, prop_mean (mean over books), stamp."""
    games = schedule.drop_nulls(["gameday", "home_team", "away_team"]).select(
        "gameday", home="home_team", away="away_team"
    )
    before = (
        lines.filter(pl.col("stamp") < pl.col("kickoff"))
        .with_columns(
            gameday=pl.col("kickoff").dt.convert_time_zone(str(EASTERN)).dt.strftime("%Y-%m-%d")
        )
        .join(games, on=["gameday", "home", "away"])
    )
    latest = before.filter(pl.col("stamp") == pl.col("stamp").max().over("event_id"))
    age = (pl.col("kickoff") - pl.col("stamp")).dt.total_minutes() / 60
    fresh = latest.filter(age <= MAX_LINE_AGE_HOURS)
    if latest.height:
        hours = fresh.select(age.min().alias("lo"), age.max().alias("hi")).row(0)
        stale = latest["event_id"].n_unique() - fresh["event_id"].n_unique()
        print(
            f"prop lines for {fresh['event_id'].n_unique()} games, snapshots {hours[0] or 0:.0f} "
            f"to {hours[1] or 0:.0f} hours before kickoff; {stale} games dropped (latest snapshot "
            f"older than {MAX_LINE_AGE_HOURS} hours)"
        )
    means = [prop_mean(*row) for row in fresh.select("market", "line", "p_over").iter_rows()]
    return (
        fresh.with_columns(pl.Series("prop_mean", means, dtype=pl.Float64))
        .group_by("home", "away", "player", "market")
        .agg(pl.col("prop_mean").mean(), pl.col("stamp").max())
    )


def map_players(lines: pl.DataFrame, people: pl.DataFrame) -> pl.DataFrame:
    """`lines` with gsis_id and position: a unique match on normalized name within the game's
    two teams (`people`: gsis_id, name, position, team), else dropped."""

    def key(df: pl.DataFrame, column: str) -> pl.DataFrame:
        return df.with_columns(
            pl.col(column).map_elements(normalize_name, return_dtype=pl.String).alias("_name")
        )

    known = key(people, "name").select("gsis_id", "position", "team", "_name").unique()
    matched = (
        key(lines, "player")
        .join(known, on="_name")
        .filter((pl.col("team") == pl.col("home")) | (pl.col("team") == pl.col("away")))
    )
    unique = matched.filter(pl.col("gsis_id").n_unique().over("home", "away", "player") == 1)
    return unique.unique(["gsis_id", "market"], keep="first").drop("_name", "team")


def lagged_means(
    points: pl.DataFrame, stats: pl.DataFrame, scoring: dict[str, float], season: int, week: int
) -> pl.DataFrame:
    """Per player, means over his last LAG_GAMES games before (season, week): each line stat,
    `rest` (his points less the line stats' points) and `unprojected` (fumble-lost and two-point
    points). `points`: one league's player_points."""
    line_stats = [stat for stat, _ in MARKETS.values()]
    extra = [c for cols in UNPROJECTED.values() for c in cols]
    before = points.filter(store.week_index() < season * store.WEEK_STRIDE + week)
    games = (
        before.select("gsis_id", "season", "week", "points")
        .join(
            stats.select(
                pl.col("player_id").alias("gsis_id"), "season", "week", *line_stats, *extra
            ),
            on=["gsis_id", "season", "week"],
            how="left",
        )
        .with_columns(pl.col(*line_stats, *extra).fill_null(0.0))
    )
    line_points = sum(pl.col(stat) * scoring.get(key, 0.0) for stat, key in MARKETS.values())
    unprojected = sum(
        scoring.get(key, 0.0) * pl.sum_horizontal(cols) for key, cols in UNPROJECTED.items()
    )
    recent = (
        games.with_columns(rest=pl.col("points") - line_points, unprojected=unprojected)
        .sort("gsis_id", "season", "week")
        .group_by("gsis_id", maintain_order=True)
        .tail(LAG_GAMES)
    )
    return recent.group_by("gsis_id").agg(
        pl.len().alias("n_games"), pl.col(*line_stats, "rest", "unprojected").mean()
    )


def implied_points(
    props: pl.DataFrame, lags: pl.DataFrame, scoring: dict[str, float], positions: Sequence[str]
) -> pl.DataFrame:
    """gsis_id, projection for players of `positions` with every PRIMARY line and a lag row.
    `props`: gsis_id, position, market, prop_mean."""
    if not positions:
        return pl.DataFrame(schema={"gsis_id": pl.String, "projection": pl.Float64})
    wide = props.group_by("gsis_id", "position").agg(
        pl.col("prop_mean").filter(pl.col("market") == m).mean().alias(m) for m in MARKETS
    )
    covered = pl.any_horizontal(
        (pl.col("position") == pos)
        & pl.all_horizontal(pl.col(m).is_not_null() for m in PRIMARY[pos])
        for pos in positions
    )
    # inner join: a player with no earlier game has no lagged touchdowns to add
    rows = wide.filter(covered).join(lags, on="gsis_id")
    x = sum(
        pl.coalesce(m, stat).fill_null(0.0) * scoring.get(key, 0.0)
        for m, (stat, key) in MARKETS.items()
    )
    return rows.select("gsis_id", projection=x + pl.col("rest"))


def outside_points(
    snaps: pl.DataFrame,
    scoring: dict[str, float],
    lags: pl.DataFrame,
    bias: dict[str, float] | None = None,
) -> pl.DataFrame:
    """Each source's latest snapshot per position (`snaps`: source, fetched_at, position, gsis_id,
    stats JSON) scored under `scoring`, plus the player's lagged `unprojected` points, less the
    position's `bias` (FFTODAY_BIAS by default; FFToday is the only source): source, gsis_id,
    fetched_at, projection."""
    bias = FFTODAY_BIAS if bias is None else bias
    newest = pl.col("fetched_at").max().over("source", "position")
    latest = snaps.filter(pl.col("fetched_at") == newest).unique(
        ["source", "gsis_id"], keep="first", maintain_order=True
    )
    scored = [score_stats(json.loads(s), scoring) for s in latest["stats"]]
    level = pl.col("position").replace_strict(bias, default=0.0, return_dtype=pl.Float64)
    return (
        latest.select("source", "gsis_id", "fetched_at", "position")
        .with_columns(pl.Series("projection", scored, dtype=pl.Float64))
        .join(lags.select("gsis_id", "unprojected"), on="gsis_id", how="left")
        .select(
            "source",
            "gsis_id",
            "fetched_at",
            projection=pl.col("projection") + pl.col("unprojected").fill_null(0.0) - level,
        )
    )


def current_people(data_dir: Path) -> pl.DataFrame:
    """gsis_id, name, position and team now, from Sleeper's players file."""
    ids = store.read_table("id_map", "derived", data_dir).select("sleeper_id", "gsis_id")
    return (
        store.read_table("sleeper_players", "raw", data_dir)
        .drop("gsis_id")
        .join(ids, on="sleeper_id")
        .select("gsis_id", pl.col("full_name").alias("name"), "position", "team")
        .with_columns(pl.col("team").map_elements(norm_team, return_dtype=pl.String))
        .drop_nulls()
    )


def window_start(schedule: pl.DataFrame) -> datetime | None:
    """00:00 Eastern on the Tuesday on or before the week's first kickoff (None: no dated game)."""
    days = schedule["gameday"].drop_nulls()
    if days.is_empty():
        return None
    first = datetime.fromisoformat(str(days.min())).replace(tzinfo=EASTERN)
    back = (first.weekday() - calendar.TUESDAY) % 7
    return (first - timedelta(days=back)).astimezone(UTC)


def _outside_snapshots(
    data_dir: Path, season: int, week: int, since: datetime | None
) -> pl.DataFrame:
    """This week's archived outside rows fetched since `since`, mapped to gsis_id; logs each
    source's age by position and warns about missing positions."""
    empty = pl.DataFrame(
        schema={s: pl.String for s in ("source", "fetched_at", "position", "gsis_id", "stats")}
    )
    try:
        snaps = store.read_table("outside_proj_snapshots", "archive", data_dir)
    except FileNotFoundError:
        return empty
    at = pl.col("fetched_at").str.to_datetime(time_zone="UTC", time_unit="us")
    snaps = snaps.filter((pl.col("season") == season) & (pl.col("week") == week))
    if since is not None:
        snaps = snaps.filter(at >= since)
    if snaps.is_empty():
        return empty
    now = datetime.now(UTC)
    for (source,), g in snaps.group_by("source"):
        ages = g.group_by("position").agg(at.max()).sort("position")
        for position, fetched in ages.iter_rows():
            hours = (now - fetched).total_seconds() / 3600
            print(f"{source} {position} fetched {hours:.0f} hours ago")
        missing = sorted(set(op.POSITIONS) - set(ages["position"]))
        if missing:
            print(f"warning: {source} has no rows for {missing} in week {week}")
    mapped = op.map_to_gsis(snaps, op.people(data_dir)).drop_nulls("gsis_id")
    return mapped.select(*empty.columns)


def _week_props(data_dir: Path, odds_dir: Path, schedule: pl.DataFrame) -> pl.DataFrame:
    """This week's mapped prop lines: gsis_id, position, market, prop_mean, stamp."""
    lines = week_lines(read_snapshots(odds_dir), schedule)
    if lines.is_empty():
        print(
            f"no odds snapshot taken within {MAX_LINE_AGE_HOURS} hours before kickoff for this "
            "week's games: no prop points (run `make odds-slate` before kickoff)"
        )
    return map_players(lines, current_people(data_dir))


def run(data_dir: Path = store.DATA_DIR, odds_dir: Path = ODDS_DIR) -> tuple[int, int]:
    """Write proj_props and proj_outside for the current week; returns their row counts."""
    config = load_config()
    leagues = store.read_table("leagues", "raw", data_dir)
    season, week = config.season, int(leagues["current_week"].to_numpy().max())
    schedule = store.read_table("nfl_schedules", "raw", data_dir).filter(
        (pl.col("season") == season) & (pl.col("week") == week)
    )
    snaps = _outside_snapshots(data_dir, season, week, window_start(schedule))
    if snaps.is_empty():
        print(f"no outside projections archived for week {week}: no FFToday points")
    points = store.read_table("player_points", "derived", data_dir)
    stats = store.read_table("nfl_player_stats", "raw", data_dir)
    lags = {
        lg["league_id"]: lagged_means(
            points.filter(pl.col("league_id") == lg["league_id"]),
            stats,
            json.loads(lg["scoring_settings"]),
            season,
            week,
        )
        for lg in leagues.iter_rows(named=True)
    }
    stamp = {"season": season, "week": week}
    outside = [
        outside_points(
            snaps, json.loads(lg["scoring_settings"]), lags[lg["league_id"]]
        ).with_columns(pl.lit(lg["league_id"]).alias("league_id"))
        for lg in leagues.iter_rows(named=True)
    ]
    try:
        props = _week_props(data_dir, odds_dir, schedule)
        fetched = props.group_by("gsis_id").agg(
            pl.col("stamp").max().dt.strftime("%Y-%m-%dT%H:%M:%S+00:00").alias("fetched_at")
        )
        implied = []
        for lg in leagues.iter_rows(named=True):
            scoring = json.loads(lg["scoring_settings"])
            rows = implied_points(props, lags[lg["league_id"]], scoring, config.prop_positions)
            implied.append(
                rows.join(fetched, on="gsis_id", how="left").with_columns(
                    pl.lit(lg["league_id"]).alias("league_id")
                )
            )
    except Exception as err:  # fail soft like outside_projections: the blend runs without props
        print(f"warning: prop points skipped for week {week}: {err!r}")
        implied = []
    tables = {
        name: _typed(name, frames, stamp)
        for name, frames in (("proj_props", implied), ("proj_outside", outside))
    }
    store.write_tables(tables, "derived", data_dir)
    return tables["proj_props"].height, tables["proj_outside"].height


def _typed(name: str, frames: list[pl.DataFrame], stamp: dict[str, int]) -> pl.DataFrame:
    schema = store.SCHEMAS[name]
    if not frames:
        return pl.DataFrame(schema=schema)
    rows = pl.concat(frames).with_columns(**{k: pl.lit(v) for k, v in stamp.items()})
    return rows.select(pl.col(column).cast(dtype) for column, dtype in schema.items())


if __name__ == "__main__":
    n_props, n_outside = run()
    print(f"prop points: {n_props} rows; outside points: {n_outside} rows")
