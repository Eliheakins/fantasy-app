"""Are weekly team scores spread as the model says? YinzBurgh's ESPN seasons as extra history.

Runs `stages.calibration.team_week_scores` on 2023 to 2025 regular-season lineups: each team's
mean and spread come from the starters' pre-game learned projections with the current spread
tables (`cv`, size tiers, same-team correlations) and league K and DEF figures; z is the actual
ESPN score (the league's own 0.5 PPR scoring, K and DEF included) against that. Targets: z mean 0,
z sd 1, 80% interval holding about 80%. The spread tables were fit on nflverse history for these
same seasons, so this is a check of the team-level assembly (correlations, K and DEF, drift), not
an out-of-sample test of the player spreads.

    uv run python research/espn_parse.py && uv run python research/espn_calibration_check.py
"""

import polars as pl

from fantasy import store
from fantasy.stages.calibration import summarize, team_week_scores
from fantasy.stages.simulate import load_league_data

SCRATCH = store.ROOT / "research" / "scratch" / "espn"


def main() -> None:
    league = store.read_table("leagues", "raw").filter(pl.col("league_key") == "yinzburgh")
    row = league.row(0, named=True)
    data = load_league_data(row)
    lineups = pl.read_parquet(SCRATCH / "lineups.parquet").filter(
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
        scores = team_week_scores(data, starters, projections, actual)
        out.append(scores.with_columns(pl.lit(season).alias("season")))
    scores = pl.concat(out).filter(pl.col("missing") == 0)
    print(f"team-weeks with every skill starter projected: {scores.height}")
    for label, frame in [*((str(k[0]), g) for k, g in scores.group_by("season", maintain_order=True)),
                         ("all", scores)]:  # fmt: skip
        s = summarize(frame)
        print(f"{label:>5} n={s['n']:.0f}  mean z {s['z_mean']:+.2f}  sd z {s['z_sd']:.2f}  "
              f"50% holds {s['coverage50']:.0%}  80% holds {s['coverage80']:.0%}")  # fmt: skip


if __name__ == "__main__":
    main()
