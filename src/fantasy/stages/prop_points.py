"""The current week's prop-implied and FFToday points per league, for the blend in simulate.

proj_props: for each of this week's games, the latest Odds API snapshot under data/archive/odds
taken before its kickoff and no earlier than STALE_DAYS before the week's first kickoff. Method of
research/props_check.py: de-vig each book's two-way prices; a yardage line L is a median, mean =
r_m * (L + z * sigma_m) with z = Phi^-1(p_over) clamped to +/-Z_CLAMP; receptions by Poisson
inversion, mean = r_m * lambda; books averaged. X (non-TD points) = league weights times those
means, the player's lagged mean for a stat without a line. Points = X + his lagged mean of every
other point (touchdowns, interceptions, fumbles, two-point conversions). Only `prop_positions`
(RB and WR) with every line of PRIMARY and at least one earlier game. 2024 held out: the equal
blend with the learned projection cut RMSE 1.6% and 1.4% (docs/decisions.md).

proj_outside: each outside source's latest snapshot of the current week (outside_projections),
scored under the league's rules plus the player's lagged mean of fumble-lost and two-point points
under that league's weights, which FFToday does not project (it ran 0.4 points high).

No network; no snapshot or a stale one leaves the table empty with a log line.
Run: uv run python -m fantasy.stages.prop_points
"""

import json
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
STALE_DAYS = 7
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
    """lambda with P(X > line) = p_over; P(X <= k - 1) = Q(k, lambda) for k = ceil(line)."""
    k = int(-(-line // 1))
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
            rows += event_lines(json.loads(file.read_text()), stamp)
    return pl.DataFrame(rows, schema=LINE_SCHEMA)


def week_lines(lines: pl.DataFrame, schedule: pl.DataFrame) -> pl.DataFrame:
    """The week's games (`schedule`: one week's rows) from each game's latest snapshot before
    kickoff and not stale: home, away, player, market, prop_mean (mean over books)."""
    if schedule.is_empty():
        return lines.clear().select(
            "home", "away", "player", "market", prop_mean="line", stamp="stamp"
        )
    kicks = (schedule["gameday"] + "T" + schedule["gametime"]).to_list()
    first = min(datetime.fromisoformat(k).replace(tzinfo=EASTERN) for k in kicks).astimezone(UTC)
    games = schedule.select("gameday", home="home_team", away="away_team")
    fresh = (
        lines.filter(
            (pl.col("stamp") < pl.col("kickoff"))
            & (pl.col("stamp") >= first - timedelta(days=STALE_DAYS))
        )
        .with_columns(
            gameday=pl.col("kickoff").dt.convert_time_zone(str(EASTERN)).dt.strftime("%Y-%m-%d")
        )
        .join(games, on=["gameday", "home", "away"])
    )
    latest = fresh.filter(pl.col("stamp") == pl.col("stamp").max().over("event_id"))
    means = [prop_mean(*row) for row in latest.select("market", "line", "p_over").iter_rows()]
    return (
        latest.with_columns(pl.Series("prop_mean", means, dtype=pl.Float64))
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
    snaps: pl.DataFrame, scoring: dict[str, float], lags: pl.DataFrame
) -> pl.DataFrame:
    """Each source's latest snapshot (`snaps`: source, fetched_at, gsis_id, stats JSON) scored
    under `scoring`, plus the player's lagged `unprojected` points: source, gsis_id, fetched_at,
    projection."""
    latest = snaps.filter(pl.col("fetched_at") == pl.col("fetched_at").max().over("source"))
    latest = latest.unique(["source", "gsis_id"], keep="first", maintain_order=True)
    scored = [score_stats(json.loads(s), scoring) for s in latest["stats"]]
    return (
        latest.select("source", "gsis_id", "fetched_at")
        .with_columns(pl.Series("projection", scored, dtype=pl.Float64))
        .join(lags.select("gsis_id", "unprojected"), on="gsis_id", how="left")
        .select(
            "source",
            "gsis_id",
            "fetched_at",
            projection=pl.col("projection") + pl.col("unprojected").fill_null(0.0),
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


def _outside_snapshots(data_dir: Path, season: int, week: int) -> pl.DataFrame:
    """This week's archived outside rows mapped to gsis_id (none: an empty frame)."""
    empty = pl.DataFrame(
        schema={
            "source": pl.String,
            "fetched_at": pl.String,
            "gsis_id": pl.String,
            "stats": pl.String,
        }
    )
    try:
        snaps = store.read_table("outside_proj_snapshots", "archive", data_dir)
    except FileNotFoundError:
        return empty
    snaps = snaps.filter((pl.col("season") == season) & (pl.col("week") == week))
    if snaps.is_empty():
        return empty
    mapped = op.map_to_gsis(snaps, op.people(data_dir)).drop_nulls("gsis_id")
    return mapped.select(*empty.columns)


def run(data_dir: Path = store.DATA_DIR, odds_dir: Path = ODDS_DIR) -> tuple[int, int]:
    """Write proj_props and proj_outside for the current week; returns their row counts."""
    config = load_config()
    leagues = store.read_table("leagues", "raw", data_dir)
    season, week = config.season, int(leagues["current_week"].to_numpy().max())
    schedule = store.read_table("nfl_schedules", "raw", data_dir).filter(
        (pl.col("season") == season) & (pl.col("week") == week)
    )
    lines = week_lines(read_snapshots(odds_dir), schedule)
    if lines.is_empty():
        print(
            f"no odds snapshot for week {week} taken before kickoff in the last {STALE_DAYS} days "
            "of the week: no prop points (run `make odds-slate` before kickoff)"
        )
    props = map_players(lines, current_people(data_dir))
    fetched = props.group_by("gsis_id").agg(
        pl.col("stamp").max().dt.strftime("%Y-%m-%dT%H:%M:%S+00:00").alias("fetched_at")
    )
    snaps = _outside_snapshots(data_dir, season, week)
    if snaps.is_empty():
        print(f"no outside projections archived for week {week}: no FFToday points")
    points = store.read_table("player_points", "derived", data_dir)
    stats = store.read_table("nfl_player_stats", "raw", data_dir)
    prop_rows, outside_rows = [], []
    for league in leagues.iter_rows(named=True):
        scoring = json.loads(league["scoring_settings"])
        lags = lagged_means(
            points.filter(pl.col("league_id") == league["league_id"]), stats, scoring, season, week
        )
        stamp = {"league_id": league["league_id"], "season": season, "week": week}
        prop_rows.append(
            implied_points(props, lags, scoring, config.prop_positions)
            .join(fetched, on="gsis_id", how="left")
            .with_columns(**{k: pl.lit(v) for k, v in stamp.items()})
        )
        outside_rows.append(
            outside_points(snaps, scoring, lags).with_columns(
                **{k: pl.lit(v) for k, v in stamp.items()}
            )
        )
    tables = {
        name: pl.concat(rows).select(
            pl.col(column).cast(dtype) for column, dtype in store.SCHEMAS[name].items()
        )
        for name, rows in (("proj_props", prop_rows), ("proj_outside", outside_rows))
    }
    store.write_tables(tables, "derived", data_dir)
    return tables["proj_props"].height, tables["proj_outside"].height


if __name__ == "__main__":
    n_props, n_outside = run()
    print(f"prop points: {n_props} rows; outside points: {n_outside} rows")
