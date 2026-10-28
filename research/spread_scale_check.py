"""Is the weekly team-score spread too wide, and does a fitted factor beat the model's as-is?

Pools the 2026 weeks played so far (both leagues, `stages.calibration`) with YinzBurgh's ESPN
seasons 2023 to 2025 (`espn_calibration_check`). Leave-one-season-out: the factor s is the
standard deviation of z (about its own mean, since a bias moves both teams of a matchup alike)
on the other three seasons; the held-out season is scored by the normal log likelihood of its
z / s. Rule, fixed before the run: ship a factor if its mean held-out log score gain is positive
in at least three of the four seasons and the paired t over all team-weeks is 2 or more.

    uv run python research/espn_parse.py && uv run python research/spread_scale_check.py
"""

import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
import espn_calibration_check as espn  # noqa: E402

from fantasy import store  # noqa: E402
from fantasy.stages.calibration import run as run_2026  # noqa: E402
from fantasy.stages.simulate import load_league_data  # noqa: E402
from fantasy.stages.calibration import team_week_scores  # noqa: E402


def espn_scores() -> pl.DataFrame:
    league = store.read_table("leagues", "raw").filter(pl.col("league_key") == "yinzburgh")
    row = league.row(0, named=True)
    data = load_league_data(row)
    lineups = pl.read_parquet(espn.SCRATCH / "lineups.parquet").filter(
        pl.col("starter") & pl.col("position").is_not_null()
    )
    out = []
    for season in (2023, 2024, 2025):
        hist = store.projection_table().filter(
            (pl.col("league_id") == row["league_id"]) & ~pl.col("is_future")
            & (pl.col("season") == season)
        )  # fmt: skip
        projections = {(r["gsis_id"], r["week"]): r["projection"] for r in hist.iter_rows(named=True)}
        mine = lineups.filter(pl.col("season") == season)
        starters = mine.select(pl.col("team_id").alias("roster_id"), "week", "gsis_id", "position")
        actual = {
            (t, w): float(p)
            for t, w, p in mine.group_by("team_id", "week").agg(pl.col("points").sum()).iter_rows()
        }
        out.append(team_week_scores(data, starters, projections, actual).with_columns(
            pl.lit(season).alias("season")))  # fmt: skip
    return pl.concat(out)


def main() -> None:
    now = run_2026().with_columns(pl.lit(2026).alias("season"))
    scores = pl.concat([espn_scores(), now.select(espn_scores().columns)]).filter(pl.col("missing") == 0)
    seasons = sorted(scores["season"].unique().to_list())
    gains = []
    for held in seasons:
        rest = scores.filter(pl.col("season") != held)["z"]
        s = float(rest.std())  # type: ignore[arg-type]
        z = scores.filter(pl.col("season") == held)["z"].to_numpy()
        centre = float(np.mean(z))  # a score bias is not a spread error: both arms use the true centre
        base = -0.5 * (z - centre) ** 2
        scaled = -np.log(s) - 0.5 * ((z - centre) / s) ** 2
        diff = scaled - base
        gains.append(diff)
        print(f"{held}: n={z.size:3d}  held-out sd z {z.std():.2f}  factor from the rest {s:.2f}  "
              f"mean log-score gain {diff.mean():+.4f}")  # fmt: skip
    pooled = np.concatenate(gains)
    t = pooled.mean() / (pooled.std(ddof=1) / np.sqrt(pooled.size))
    print(f"pooled gain {pooled.mean():+.4f} per team-week, t {t:.2f}; "
          f"seasons with a gain: {sum(g.mean() > 0 for g in gains)} of {len(gains)}")  # fmt: skip


if __name__ == "__main__":
    main()
