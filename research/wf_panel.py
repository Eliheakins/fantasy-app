"""Shared panel and scoring for `stack_check.py` and `settings_check.py`.

`panel(lid)`: the learned model's one-game-ahead feature rows with points for one league, built by
the same code as `learn.history_forecasts(1)`, cached under research/scratch/.
`calibrated_baseline()`: proj_baseline size-calibrated per season with curves fit on earlier
seasons only, as `learn.compare_to_baseline` does.
`score(...)`: the held-out report (RMSE, MAE, mean error, by position and season, paired per-week
t on squared-error differences against a reference column, weeks better).
"""

from collections.abc import Callable
from pathlib import Path

import numpy as np
import polars as pl

from fantasy import store
from fantasy.sim.calibration import apply_curves
from fantasy.stages.distributions import estimate_curves, residual_frame
from fantasy.stages.learn import (
    MIN_PROJECTION,
    build_features,
    games_frame,
    load_extras,
    state_frame,
    train_seasons,
    walk_forward,
)
from fantasy.stages.project import GROUP, expected_frame, history_targets

SCRATCH = Path(__file__).parent / "scratch"
KEY = [*GROUP, "season", "week"]
LEAGUE_NAMES = {}  # filled lazily: league_id -> short name


def league_ids() -> list[str]:
    leagues = store.read_table("leagues", "raw")
    for row in leagues.iter_rows(named=True):
        LEAGUE_NAMES[row["league_id"]] = row["league_key"]
    return [str(x) for x in leagues["league_id"].to_list()]


def walk(
    history: pl.DataFrame,
    fit: Callable[[pl.DataFrame, pl.DataFrame], np.ndarray],
    seasons: list[int],
) -> pl.DataFrame:
    """KEY + `pred` for each season in `seasons`, from `fit(train, test)` on the seasons
    `learn.train_seasons` allows (earlier ones, or the early block)."""
    available = sorted(history["season"].unique().to_list())
    parts = []
    for season in seasons:
        train = history.filter(pl.col("season").is_in(train_seasons(season, available)))
        test = history.filter(pl.col("season") == season)
        parts.append(test.select(KEY).with_columns(pl.Series("pred", fit(train, test))))
    return pl.concat(parts)


def learned_oof() -> pl.DataFrame:
    """The current model's walk-forward projections, recomputed from code (cached), with the
    max absolute difference from `proj_learned` printed."""
    path = SCRATCH / "learned_oof.parquet"
    if not path.exists():
        parts = [
            walk_forward(panel(lid)).select(*KEY, "position", "points", "projection")
            for lid in league_ids()
        ]
        pl.concat(parts).rename({"projection": "learned"}).write_parquet(path)
    oof = pl.read_parquet(path)
    stored = store.read_table("proj_learned").filter(~pl.col("is_future"))
    both = oof.join(stored.select(*KEY, "projection"), on=KEY, how="inner")
    diff = (both["learned"] - both["projection"]).abs().max()
    print(
        f"reproduction: {both.height} of {oof.height} recomputed rows matched proj_learned "
        f"({stored.height} stored past rows); max abs diff {diff}"
    )
    return oof


def build_panels() -> None:
    leagues = store.read_table("leagues", "raw")
    opp = store.read_table("nfl_ff_opportunity", "raw")
    exp = expected_frame(opp, store.read_table("player_points"), leagues)
    games_all = games_frame(
        exp, opp, store.read_table("nfl_snaps", "raw"), store.read_table("nfl_player_stats", "raw")
    )
    lines = store.read_table("team_games")
    extras = load_extras()
    SCRATCH.mkdir(exist_ok=True)
    for lid in leagues["league_id"].to_list():
        games = games_all.filter(pl.col("league_id") == lid)
        targets = history_targets(exp.filter(pl.col("league_id") == lid))
        history = build_features(targets, state_frame(games), lines, extras, 1).join(
            games.select(*GROUP, "season", "week", "points"), on=KEY
        )
        history.write_parquet(SCRATCH / f"panel_{lid}.parquet")


def panel(lid: str) -> pl.DataFrame:
    path = SCRATCH / f"panel_{lid}.parquet"
    if not path.exists():
        build_panels()
    return pl.read_parquet(path)


def calibrated_baseline(first_season: int = 2021) -> pl.DataFrame:
    """KEY, position, has_history, `baseline` (size-calibrated with earlier seasons' curves)."""
    baseline = store.read_table("proj_baseline").filter(~pl.col("is_future"))
    history = residual_frame(baseline, store.read_table("player_points"))
    parts = []
    for (league_id,), league_base in baseline.group_by("league_id"):
        seasons = sorted(s for s in league_base["season"].unique().to_list() if s >= first_season)
        for season in seasons:
            curves = estimate_curves(
                history.filter((pl.col("league_id") == league_id) & (pl.col("season") < season))
            )
            parts.append(apply_curves(league_base.filter(pl.col("season") == season), curves))
    return pl.concat(parts).select(*KEY, "has_history", pl.col("projection").alias("baseline"))


def scored_rows(frame: pl.DataFrame, base: pl.DataFrame) -> pl.DataFrame:
    """The compare_to_baseline population: has_history and calibrated baseline above 3 points."""
    keep = base.filter(pl.col("has_history") & (pl.col("baseline") > MIN_PROJECTION))
    return frame.join(keep.select(*KEY, "baseline"), on=KEY, how="inner")


def paired(data: pl.DataFrame, cand: str, ref: str) -> tuple[float, int, int]:
    """Paired per-week t on squared-error differences (positive: candidate better)."""
    by_week = data.group_by("season", "week").agg(
        ((pl.col("points") - pl.col(ref)) ** 2).mean().alias("r"),
        ((pl.col("points") - pl.col(cand)) ** 2).mean().alias("c"),
    )
    diff = (by_week["r"] - by_week["c"]).to_numpy()
    t = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))) if len(diff) > 1 else 0.0
    return t, int((diff > 0).sum()), len(diff)


def metrics(data: pl.DataFrame, col: str) -> dict[str, float]:
    err = data["points"].to_numpy() - data[col].to_numpy()
    return {
        "rmse": float(np.sqrt((err**2).mean())),
        "mae": float(np.abs(err).mean()),
        "me": float(-err.mean()),  # projection minus points
    }


def report(data: pl.DataFrame, cands: list[str], ref: str = "learned") -> pl.DataFrame:
    """One row per league, slice (all, season, position) and candidate."""
    rows = []
    for (lid,), g in data.group_by("league_id", maintain_order=True):
        slices = [("all", g)]
        slices += [(f"s{s}", g.filter(pl.col("season") == s)) for s in sorted(g["season"].unique())]
        slices += [(p, g.filter(pl.col("position") == p)) for p in ("QB", "RB", "WR", "TE")]
        for name, part in slices:
            r = metrics(part, ref)
            for cand in cands:
                m = metrics(part, cand)
                t, better, weeks = paired(part, cand, ref)
                rows.append(
                    {
                        "league": LEAGUE_NAMES.get(lid, lid),
                        "slice": name,
                        "cand": cand,
                        "n": part.height,
                        "rmse": round(m["rmse"], 4),
                        "rmse_ref": round(r["rmse"], 4),
                        "gain_pct": round(100 * (r["rmse"] - m["rmse"]) / r["rmse"], 2),
                        "mae": round(m["mae"], 4),
                        "me": round(m["me"], 3),
                        "t": round(t, 2),
                        "better": f"{better}/{weeks}",
                    }
                )
    return pl.DataFrame(rows)
