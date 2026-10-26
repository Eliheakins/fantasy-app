"""Check the weekly team-score distributions against what happened in completed 2026 weeks.

For each team-week, the starters that were actually set get the same mean and variance the season
simulator uses (projection made before the game, measured spread and teammate correlations, K and
DEF constants, plus team drift). The standardized miss z = (actual - mean) / sd should have mean 0,
spread 1, and an 80% interval that holds about 80% of outcomes.

Projections get the size calibration the simulation applies, with curves refit on seasons before
the one being scored, so the scored weeks play no part in the fit. (Spreads and correlations are
still fit on every week, this season's included, about 4% of the data.)

Run: uv run python -m fantasy.stages.calibration
"""

import math
from typing import Any

import polars as pl

from fantasy import store
from fantasy.sim.calibration import apply_curves
from fantasy.sim.lineup import Player
from fantasy.sim.odds import DRIFT_SD, LeagueData, lineup_moments
from fantasy.stages.distributions import estimate_curves, residual_frame
from fantasy.stages.simulate import load_league_data
from fantasy.store import SKILL

Z80 = 1.2815515655446004  # 80% two-sided
Z50 = 0.6744897501960817


def team_week_scores(
    data: LeagueData,
    starters: pl.DataFrame,
    projections: dict[tuple[str, int], float],
    actual: dict[tuple[int, int], float],
) -> pl.DataFrame:
    """starters: roster_id, week, gsis_id, position. projections: (gsis_id, week) -> points."""
    rows: list[dict[str, Any]] = []
    for (roster_id, week), g in starters.group_by("roster_id", "week"):
        skill = g.filter(pl.col("position").is_in(SKILL))
        players, missing = [], 0
        for r in skill.iter_rows(named=True):
            value = projections.get((r["gsis_id"], week)) if r["gsis_id"] else None
            if value is None:
                missing += 1
            else:
                players.append(Player(r["gsis_id"], r["position"], value))
        k = g.filter(pl.col("position") == "K").height
        d = g.filter(pl.col("position") == "DEF").height
        mean, var, _ = lineup_moments(players, data.cv, data.pair_rho, data.cv_tiers)
        mean += k * data.k_mean + d * data.def_mean
        var += k * data.k_var + d * data.def_var + DRIFT_SD**2
        sd = math.sqrt(var)
        points = actual[(int(roster_id), int(week))]
        rows.append(
            {
                "roster_id": int(roster_id),
                "week": int(week),
                "actual": points,
                "mean": mean,
                "sd": sd,
                "z": (points - mean) / sd,
                "missing": missing,
            }
        )
    schema = {
        "roster_id": pl.Int64,
        "week": pl.Int64,
        "actual": pl.Float64,
        "mean": pl.Float64,
        "sd": pl.Float64,
        "z": pl.Float64,
        "missing": pl.Int64,
    }
    return pl.DataFrame(rows, schema=schema)


def summarize(scores: pl.DataFrame) -> dict[str, float]:
    z = scores["z"]
    return {
        "n": float(scores.height),
        "z_mean": float(z.mean() or 0.0),  # type: ignore[arg-type]
        "z_sd": float(z.std() or 0.0),  # type: ignore[arg-type]
        "coverage50": float((z.abs() <= Z50).mean() or 0.0),  # type: ignore[arg-type]
        "coverage80": float((z.abs() <= Z80).mean() or 0.0),  # type: ignore[arg-type]
    }


def run() -> pl.DataFrame:
    id_map = store.read_table("id_map").select("sleeper_id", "gsis_id")
    players = store.read_table("sleeper_players", "raw").select("sleeper_id", "position")
    out = []
    history = residual_frame(store.projection_table(), store.read_table("player_points"))
    for league in store.read_table("leagues", "raw").iter_rows(named=True):
        lid, season = league["league_id"], int(league["season"])
        last = int(league["current_week"]) - 1
        data = load_league_data(league)
        starters = (
            store.read_table("matchup_players", "raw")
            .filter((pl.col("league_id") == lid) & (pl.col("week") <= last) & pl.col("is_starter"))
            .join(players, on="sleeper_id")
            .join(id_map, on="sleeper_id", how="left")
            .select("roster_id", "week", "gsis_id", "position")
        )
        hist = store.projection_table().filter(
            (pl.col("league_id") == lid) & ~pl.col("is_future") & (pl.col("season") == season)
        )
        if store.projection_name() != "proj_learned":  # used uncalibrated (`calibrated`)
            hist = apply_curves(hist, estimate_curves(history.filter(pl.col("season") < season)))
        projections = {
            (r["gsis_id"], r["week"]): r["projection"] for r in hist.iter_rows(named=True)
        }
        matchups = store.read_table("matchups", "raw").filter(pl.col("league_id") == lid)
        actual = {(r["roster_id"], r["week"]): r["points"] for r in matchups.iter_rows(named=True)}
        out.append(
            team_week_scores(data, starters, projections, actual).with_columns(
                pl.lit(league["league_key"]).alias("league_key")
            )
        )
    return pl.concat(out)


def main() -> None:
    scores = run()
    complete = scores.filter(pl.col("missing") == 0)
    print(f"team-weeks: {scores.height}; with every skill starter projected: {complete.height}")
    for label, frame in (("all", scores), ("complete", complete)):
        s = summarize(frame)
        print(
            f"{label:9s} n={s['n']:.0f}  mean z {s['z_mean']:+.2f}  sd z {s['z_sd']:.2f}  "
            f"50% interval holds {s['coverage50']:.0%}  80% interval holds {s['coverage80']:.0%}"
        )
    by_league = complete.group_by("league_key").agg(
        pl.len().alias("n"),
        pl.col("z").mean().round(2).alias("z_mean"),
        pl.col("z").std().round(2).alias("z_sd"),
        (pl.col("z").abs() <= Z80).mean().round(3).alias("cov80"),
    )
    print(by_league)


if __name__ == "__main__":
    main()
