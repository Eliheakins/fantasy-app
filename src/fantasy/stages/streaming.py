"""Team-defense scoring and K and DEF projections for streaming.

DEF points come from nflverse team stats under each league's scoring: sacks, interceptions,
fumble recoveries, forced fumbles, safeties, blocks, defensive and special-teams TDs, plus the
points-allowed and yards-allowed tiers. Points allowed exclude touchdowns the opponent's defense
and special teams scored. This matches Sleeper exactly in most team-weeks (52 of 60 for Colgate,
41 of 60 for YinzBurgh, weeks 1 to 6); the rest differ by a point or two, likely special-teams
recoveries that team stats do not carry.

Projection = recent form shrunk toward the league average, plus a slope on the game's implied
total (opponent's for DEF, own team's for K, fit on 2018 onward) and a dome adjustment for K.

Run: uv run python -m fantasy.stages.streaming
"""

import json
import re

import numpy as np
import polars as pl

from fantasy import store
from fantasy.sim.blend import blend
from fantasy.stages.crosswalk import TEAM_MAP

HALF_LIFE = 4.0  # games
SHRINK_K = 3.0  # pseudo-games of league average
DOMES = ("dome", "closed")
SCORED_FROM = 2018
BACKTEST_FROM = 2024
KINDS = ("DEF", "K")


def tier_terms(scoring: dict[str, float], prefix: str) -> list[tuple[int, int, float]]:
    """(low, high, points) for keys like pts_allow_7_13, pts_allow_0 and pts_allow_35p."""
    terms = []
    for key, weight in scoring.items():
        match = re.fullmatch(prefix + r"_(\d+)(?:_(\d+)|(p))?", key)
        if not match or not weight:
            continue
        low = int(match.group(1))
        high = 10**6 if match.group(3) else int(match.group(2) or low)
        terms.append((low, high, float(weight)))
    return terms


def tier_expr(column: str, terms: list[tuple[int, int, float]]) -> pl.Expr:
    expr = pl.lit(0.0)
    for low, high, weight in terms:
        expr = (
            pl.when((pl.col(column) >= low) & (pl.col(column) <= high))
            .then(pl.lit(weight))
            .otherwise(expr)
        )
    return expr


def defense_points_frame(
    team_stats: pl.DataFrame, team_games: pl.DataFrame, scoring: dict[str, float], league_id: str
) -> pl.DataFrame:
    """One row per team-game with the DEF points a Sleeper defense would score."""
    stats = team_stats.filter(pl.col("season_type") == "REG")
    opponent = stats.select(
        pl.col("team").alias("opponent_team"),
        "season",
        "week",
        yards_allowed=pl.col("passing_yards") + pl.col("rushing_yards"),
        opp_def_tds=pl.col("def_tds"),
        opp_st_tds=pl.col("special_teams_tds"),
    )
    games = team_games.select(
        "season", "week", "team", "points_against", "team_implied", "opp_implied", "roof"
    )
    rows = (
        stats.join(games, on=["season", "week", "team"])
        .join(opponent, on=["season", "week", "opponent_team"])
        .filter(pl.col("points_against").is_not_null())
        .with_columns(
            allowed=pl.col("points_against") - 6 * pl.col("opp_def_tds") - 6 * pl.col("opp_st_tds")
        )
    )
    plays = (
        pl.col("def_sacks") * scoring.get("sack", 0.0)
        + pl.col("def_interceptions") * scoring.get("int", 0.0)
        + pl.col("fumble_recovery_opp") * scoring.get("fum_rec", 0.0)
        + pl.col("def_fumbles_forced") * scoring.get("ff", 0.0)
        + pl.col("def_safeties") * scoring.get("safe", 0.0)
        + (pl.col("def_fg_blocks") + pl.col("def_pat_blocks") + pl.col("def_punt_blocks"))
        * scoring.get("blk_kick", 0.0)
        + pl.col("def_tds") * scoring.get("def_td", 0.0)
        + pl.col("special_teams_tds") * scoring.get("def_st_td", 0.0)
    )
    return rows.select(
        pl.lit(league_id).alias("league_id"),
        "team",
        "season",
        "week",
        (
            plays
            + tier_expr("allowed", tier_terms(scoring, "pts_allow"))
            + tier_expr("yards_allowed", tier_terms(scoring, "yds_allow"))
        ).alias("points"),
        "team_implied",
        "opp_implied",
        "roof",
    ).select(*store.SCHEMAS["defense_points"])


def shrunk_form(prior: np.ndarray, league_mean: float) -> float:
    """Exponentially weighted mean of past points (newest last), pulled toward the league mean."""
    if prior.size == 0:
        return league_mean
    weights = 0.5 ** (np.arange(prior.size)[::-1] / HALF_LIFE)
    total = float(weights.sum())
    return (float((weights * prior).sum()) + SHRINK_K * league_mean) / (total + SHRINK_K)


def fit_context(history: pl.DataFrame, implied: str) -> tuple[float, float]:
    """(slope on the implied total, extra points in a dome) by least squares on history."""
    rows = history.filter(pl.col(implied).is_not_null()).select("points", implied, "roof")
    if rows.height < 50:
        return 0.0, 0.0
    x = rows[implied].to_numpy() - rows[implied].mean()
    dome = rows["roof"].is_in(DOMES).cast(pl.Float64).to_numpy()
    design = np.column_stack([np.ones_like(x), x, dome])
    coef, *_ = np.linalg.lstsq(design, rows["points"].to_numpy(), rcond=None)
    return float(coef[1]), float(coef[2])


def project_units(
    history: pl.DataFrame,
    upcoming: pl.DataFrame,
    unit: str,
    implied: str,
    use_dome: bool,
) -> pl.DataFrame:
    """Projection for each upcoming (unit, week). `history` has unit, season, week, points,
    <implied>, roof. `upcoming` has unit, team, week, <implied>, roof."""
    league_mean = float(np.mean(history["points"].to_numpy()))
    slope, dome_bonus = fit_context(history, implied)
    centre = float(np.mean(history[implied].drop_nulls().to_numpy()))
    ordered = history.sort(unit, "season", "week")
    form = {
        key: shrunk_form(g["points"].to_numpy(), league_mean)
        for (key,), g in ordered.group_by(unit, maintain_order=True)
    }
    rows = []
    for r in upcoming.iter_rows(named=True):
        base = form.get(r[unit], league_mean)
        value = r[implied]
        adjust = slope * (value - centre) if value is not None else 0.0
        if use_dome and r["roof"] in DOMES:
            adjust += dome_bonus
        rows.append((r[unit], r["team"], r["week"], base + adjust))
    return pl.DataFrame(rows, schema=[unit, "team", "week", "projection"], orient="row")


def backtest(history: pl.DataFrame, unit: str, implied: str, use_dome: bool) -> tuple[float, float]:
    """RMSE of the walk-forward projection and of the league mean, on seasons 2024 onward."""
    test = history.filter(pl.col("season") >= BACKTEST_FROM)
    errs_model, errs_mean = [], []
    for (season, week), games in test.group_by("season", "week"):
        past = history.filter(
            (pl.col("season") < season) | ((pl.col("season") == season) & (pl.col("week") < week))
        )
        upcoming = games.select(unit, pl.col(unit).alias("team"), "week", implied, "roof")
        proj = project_units(past, upcoming, unit, implied, use_dome)
        joined = games.join(proj.select(unit, "projection"), on=unit)
        mean = float(np.mean(past["points"].to_numpy()))
        errs_model += list((joined["points"] - joined["projection"]).to_numpy())
        errs_mean += list((joined["points"] - mean).to_numpy())
    return float(np.sqrt(np.mean(np.square(errs_model)))), float(
        np.sqrt(np.mean(np.square(errs_mean)))
    )


def sleeper_by_unit(league_id: str, id_map: pl.DataFrame) -> pl.DataFrame:
    """Sleeper's projections keyed like ours: nflverse team code for DEF, gsis id for K."""
    try:
        theirs = store.read_table("proj_sleeper").filter(pl.col("league_id") == league_id)
    except FileNotFoundError:
        return pl.DataFrame(schema={"unit": pl.String, "week": pl.Int64, "other": pl.Float64})
    teams = theirs.filter(pl.col("sleeper_id").str.contains(r"^[A-Z]{2,3}$")).select(
        pl.col("sleeper_id").replace_strict(TEAM_MAP, default=pl.col("sleeper_id")).alias("unit"),
        "week",
        other=pl.col("projection"),
    )
    kickers = theirs.join(id_map.select("sleeper_id", "gsis_id"), on="sleeper_id").select(
        pl.col("gsis_id").alias("unit"), "week", other=pl.col("projection")
    )
    return pl.concat([teams, kickers])


def run() -> dict[str, tuple[float, float]]:
    games = store.read_table("team_games")
    stats = store.read_table("nfl_team_stats", "raw")
    leagues = store.read_table("leagues", "raw")
    kickers = store.read_table("player_points").filter(pl.col("position") == "K")
    sleeper = store.read_table("sleeper_players", "raw").filter(
        (pl.col("position") == "K") & (pl.col("status") == "Active") & pl.col("team").is_not_null()
    )
    id_map = store.read_table("id_map").select("sleeper_id", "gsis_id", "nfl_team")
    active_k = sleeper.select("sleeper_id").join(id_map, on="sleeper_id").drop_nulls("gsis_id")
    defense_frames, projections, report = [], [], {}
    for lg in leagues.iter_rows(named=True):
        lid, current = lg["league_id"], int(lg["current_week"])
        scoring = json.loads(lg["scoring_settings"])
        points = defense_points_frame(stats, games, scoring, lid).filter(
            pl.col("season") >= SCORED_FROM
        )
        defense_frames.append(points)
        season = int(points["season"].to_numpy().max())
        past = points.filter((pl.col("season") < season) | (pl.col("week") < current))
        ahead = games.filter((pl.col("season") == season) & (pl.col("week") >= current)).select(
            pl.col("team").alias("unit"),
            "team",
            "week",
            pl.col("opp_implied").alias("implied"),
            "roof",
        )
        d_hist = past.rename({"team": "unit", "opp_implied": "implied"})
        d_proj = project_units(d_hist, ahead, "unit", "implied", use_dome=False)
        d_proj = blend(d_proj, sleeper_by_unit(lid, id_map), "unit")
        projections.append(
            d_proj.with_columns(pl.lit(lid).alias("league_id"), pl.lit("DEF").alias("kind"))
        )
        report[f"{lg['league_key']} DEF rmse (model, mean)"] = backtest(
            d_hist, "unit", "implied", use_dome=False
        )

        k_hist = kickers.filter((pl.col("league_id") == lid) & (pl.col("season") >= SCORED_FROM))
        k_hist = k_hist.select(
            pl.col("gsis_id").alias("unit"),
            "season",
            "week",
            "points",
            pl.col("team_implied").alias("implied"),
            "roof",
        )
        k_ahead = active_k.join(
            games.filter((pl.col("season") == season) & (pl.col("week") >= current)),
            left_on="nfl_team",
            right_on="team",
        ).select(
            pl.col("gsis_id").alias("unit"),
            pl.col("nfl_team").alias("team"),
            "week",
            pl.col("team_implied").alias("implied"),
            "roof",
        )
        k_proj = project_units(k_hist, k_ahead, "unit", "implied", use_dome=True)
        k_proj = blend(k_proj, sleeper_by_unit(lid, id_map), "unit")
        projections.append(
            k_proj.with_columns(pl.lit(lid).alias("league_id"), pl.lit("K").alias("kind"))
        )
        report[f"{lg['league_key']} K rmse (model, mean)"] = backtest(
            k_hist, "unit", "implied", use_dome=True
        )
    store.write_table("defense_points", pl.concat(defense_frames))
    out = pl.concat(projections).select("league_id", "kind", "unit", "team", "week", "projection")
    store.write_table("streaming_projection", out)
    return report


def main() -> None:
    for name, (model, mean) in run().items():
        print(f"{name}: {model:.2f} vs {mean:.2f}")


if __name__ == "__main__":
    main()
