"""Panel behind the FantasyData tests: one row per league, player and week for 2019 to 2021.

FantasyData weekly stat projections come from the open `thecodeforest/fantasyfootball` repo
(2018 to 2021, one csv per week, about 300 players a week). Each stat line is rescored under the
league's own rules (fumbles and two-point conversions are not projected, so they are left out) and
joined to our baseline, the points the player scored, the volume he actually had, his trailing
volume before the game, and the game's context.

Names are matched to nflverse ids on the normalized name for the same season and week, then for
the same season (which also catches players who did not play that week).

Cached in research/scratch/ (gitignored). Build: uv run python research/fd_panel.py
"""

import csv
import io
import json
import urllib.request
from pathlib import Path

import polars as pl

from fantasy import store
from fantasy.stages.crosswalk import normalize_name
from fantasy.sim.calibration import apply_curves
from fantasy.stages.distributions import estimate_curves, residual_frame

SCRATCH = Path(__file__).parent / "scratch"
BASE = (
    "https://raw.githubusercontent.com/thecodeforest/fantasyfootball/main/"
    "examples/benchmarking_data/season/"
)
SEASONS = (2019, 2020, 2021)
STATS = [
    "passing_cmp",
    "passing_att",
    "passing_yds",
    "passing_td",
    "passing_int",
    "rushing_att",
    "rushing_yds",
    "rushing_td",
    "receiving_tgts",
    "receiving_rec",
    "receiving_yds",
    "receiving_td",
]
HALF_LIFE = 4.0  # games, as in the baseline


def fetch(season: int, week: int) -> list[dict[str, str]]:
    path = SCRATCH / "fd" / f"{season}_wk{week}.csv"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            f"{BASE}{season}/wk{week}.csv", headers={"User-Agent": "Mozilla/5.0"}
        )
        path.write_text(urllib.request.urlopen(request, timeout=60).read().decode())
    return [{**r, "season": str(season)} for r in csv.DictReader(io.StringIO(path.read_text()))]


def load_fantasydata() -> pl.DataFrame:
    rows = [r for s in SEASONS for w in range(1, 18) for r in fetch(s, w)]
    return pl.DataFrame(rows).with_columns(
        [pl.col(c).cast(pl.Float64, strict=False).fill_null(0.0) for c in STATS]
        + [pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64)]
    )


def _key(column: str) -> pl.Expr:
    return pl.col(column).map_elements(normalize_name, return_dtype=pl.String).alias("key")


def with_ids(fd: pl.DataFrame, stats: pl.DataFrame) -> pl.DataFrame:
    """Add gsis_id by normalized name: same season and week first, same season second."""
    named = stats.with_columns(_key("player_display_name")).select(
        "key", pl.col("player_id").alias("gsis_id"), "season", "week"
    )
    by_week = named.unique(["key", "season", "week"])
    by_season = (
        named.group_by("key", "season")
        .agg(pl.col("gsis_id").first().alias("gsis_season"), pl.col("gsis_id").n_unique().alias("n"))
        .filter(pl.col("n") == 1)
        .drop("n")
    )
    joined = (
        fd.with_columns(_key("name"))
        .join(by_week, on=["key", "season", "week"], how="left")
        .join(by_season, on=["key", "season"], how="left")
    )
    return joined.with_columns(pl.coalesce("gsis_id", "gsis_season").alias("gsis_id")).drop(
        "gsis_season", "key"
    )


def rescore(scoring: dict[str, float]) -> pl.Expr:
    return (
        scoring.get("pass_yd", 0.0) * pl.col("passing_yds")
        + scoring.get("pass_td", 0.0) * pl.col("passing_td")
        + scoring.get("pass_int", 0.0) * pl.col("passing_int")
        + scoring.get("rush_yd", 0.0) * pl.col("rushing_yds")
        + scoring.get("rush_td", 0.0) * pl.col("rushing_td")
        + scoring.get("rec", 0.0) * pl.col("receiving_rec")
        + scoring.get("rec_yd", 0.0) * pl.col("receiving_yds")
        + scoring.get("rec_td", 0.0) * pl.col("receiving_td")
    )


def trailing_volume(stats: pl.DataFrame) -> pl.DataFrame:
    """Each player's exponentially weighted volume over his earlier games (before this one),
    next to the volume he actually had."""
    cols = ["targets", "carries", "attempts", "receiving_yards", "rushing_yards", "passing_yards"]
    ordered = stats.filter(pl.col("season_type") == "REG").sort("player_id", "season", "week")
    return ordered.select(
        pl.col("player_id").alias("gsis_id"),
        "season",
        "week",
        *[
            pl.col(c).ewm_mean(half_life=HALF_LIFE).shift(1).over("player_id").alias(f"trail_{c}")
            for c in cols
        ],
        *[pl.col(c).alias(f"actual_{c}") for c in cols],
    )


def loso_calibrated(base: pl.DataFrame, league_id: str) -> pl.DataFrame:
    """Our projection with the size calibration refit without the season being scored, so the
    scored seasons play no part in the curves."""
    points = store.read_table("player_points").filter(pl.col("league_id") == league_id)
    history = residual_frame(base, points)
    parts = []
    for season in SEASONS:
        curves = estimate_curves(history.filter(pl.col("season") != season))
        parts.append(apply_curves(base.filter(pl.col("season") == season), curves))
    return pl.concat(parts)


def build() -> pl.DataFrame:
    stats = store.read_table("nfl_player_stats", "raw")
    fd = with_ids(load_fantasydata(), stats.filter(pl.col("season_type") == "REG"))
    volume = trailing_volume(stats)
    games = store.read_table("team_games").select(
        "season", "week", pl.col("team").alias("team_code"), "team_implied", "total_line", "points_for"
    )
    out = []
    for league in store.read_table("leagues", "raw").iter_rows(named=True):
        lid, scoring = league["league_id"], json.loads(league["scoring_settings"])
        base = store.read_table("proj_baseline").filter(
            (pl.col("league_id") == lid) & ~pl.col("is_future")
        )
        ours = loso_calibrated(base, lid).select(
            "gsis_id", "season", "week", pl.col("projection").alias("ours"), "has_history", "team"
        )
        raw = base.select("gsis_id", "season", "week", pl.col("projection").alias("ours_raw"))
        actual = (
            store.read_table("player_points")
            .filter(pl.col("league_id") == lid)
            .select("gsis_id", "season", "week", pl.col("points").alias("actual"))
        )
        keys = ["gsis_id", "season", "week"]
        frame = (
            fd.filter(pl.col("gsis_id").is_not_null())
            .with_columns(rescore(scoring).alias("fd"))
            .join(ours.rename({"team": "team_ours"}), on=keys, how="left")
            .join(raw, on=keys, how="left")
            .join(actual, on=keys, how="left")
            .join(volume, on=keys, how="left")
            .with_columns(
                pl.col("actual").is_not_null().alias("played"),
                pl.lit(league["league_key"]).alias("league_key"),
                pl.coalesce("team_ours", "team").alias("team_code"),
            )
            .join(games, on=["season", "week", "team_code"], how="left")
        )
        out.append(frame)
    return pl.concat(out, how="diagonal_relaxed")


def main() -> None:
    panel = build()
    SCRATCH.mkdir(exist_ok=True)
    panel.write_parquet(SCRATCH / "fd_panel.parquet")
    one = panel.filter(pl.col("league_key") == panel["league_key"][0])
    print(
        f"{one.height} FantasyData rows with an id; played {one['played'].sum()}; "
        f"with our projection {one['ours'].is_not_null().sum()}"
    )


if __name__ == "__main__":
    main()
