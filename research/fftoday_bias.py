"""FFToday's level bias by position: fit on 2025, check on 2026 weeks 1 to 6.

Rows as in outside_history.py (FFToday's cached top 50 per position, mapped to gsis_id, with our
walk-forward learned projection and a stat line). FFToday is scored as prop_points does it: the
league's rules plus the player's lagged fumble-lost and two-point points. Rule (fixed before
looking): bias per league and position = mean(FFToday - actual) on 2025 weeks 1 to 6; the shipped
constant per position is the mean of the two leagues' biases. On 2026 weeks 1 to 6 compare (ours + FFToday) / 2 against
(ours + FFToday - bias) / 2 by position: RMSE and paired weekly t on squared error (negative:
corrected is better). Keep the correction only if no position gets worse with |t| >= 2 and the
pooled RMSE does not rise.

Needs the cache of outside_history.py (research/scratch/fftoday, 2025 and 2026 weeks 1 to 6).
Run from the repo root: uv run python research/fftoday_bias.py
"""

import json

import polars as pl

import outside_history as oh
from fantasy import store
from fantasy.stages import outside_projections as op
from fantasy.stages import prop_points as pp

FIT, TEST = 2025, 2026
oh.SEASONS = (FIT, TEST)


def rows(league: dict, mapped: pl.DataFrame) -> pl.DataFrame:
    lid = league["league_id"]
    scoring = json.loads(league["scoring_settings"])
    points = store.read_table("player_points").filter(pl.col("league_id") == lid)
    stats = store.read_table("nfl_player_stats", "raw")
    parts = []
    for (season, week), g in mapped.group_by("season", "week"):
        lags = pp.lagged_means(points, stats, scoring, int(season), int(week))
        snaps = g.select("position", "gsis_id", "stats", source=pl.lit("fftoday"), fetched_at=pl.lit("x"))
        parts.append(
            pp.outside_points(snaps, scoring, lags, bias={})
            .join(g.select("gsis_id", "position").unique("gsis_id"), on="gsis_id")
            .select("gsis_id", "position", "projection", season=pl.lit(season), week=pl.lit(week))
        )
    ff = pl.concat(parts).rename({"projection": "fftoday"})
    ours = (
        store.read_table("proj_learned")
        .filter((pl.col("league_id") == lid) & ~pl.col("is_future"))
        .select("gsis_id", "season", "week", pl.col("projection").alias("ours"))
    )
    actual = points.select("gsis_id", "season", "week", "points")
    keys = ["gsis_id", "season", "week"]
    return ff.join(ours, on=keys).join(actual, on=keys)


def main() -> None:
    raw = oh.fftoday_rows()
    mapped = op.map_to_gsis(raw, op.people()).drop_nulls("gsis_id")
    biases = {}
    tests = {}
    for league in store.read_table("leagues", "raw").iter_rows(named=True):
        d = rows(league, mapped)
        fit = d.filter(pl.col("season") == FIT)
        bias = dict(fit.group_by("position").agg((pl.col("fftoday") - pl.col("points")).mean()).iter_rows())
        biases[league["name"]] = bias
        tests[league["name"]] = d.filter(pl.col("season") == TEST)
        print(f"{league['name']}: 2025 rows {fit.height}, bias {({k: round(v, 3) for k, v in sorted(bias.items())})}")
    shipped = {p: sum(b[p] for b in biases.values()) / len(biases) for p in op.POSITIONS}
    print(f"shipped (mean of leagues): {({k: round(v, 2) for k, v in shipped.items()})}")
    for name, d in tests.items():
        d = d.with_columns(
            uncorrected=(pl.col("ours") + pl.col("fftoday")) / 2,
            corrected=(pl.col("ours") + pl.col("fftoday") - pl.col("position").replace_strict(shipped)) / 2,
        )
        out = []
        for pos in [None, *op.POSITIONS]:
            g = d if pos is None else d.filter(pl.col("position") == pos)
            out.append(
                {
                    "position": pos or "ALL",
                    "n": g.height,
                    "rmse_uncorrected": float(((g["uncorrected"] - g["points"]) ** 2).mean() ** 0.5),
                    "rmse_corrected": float(((g["corrected"] - g["points"]) ** 2).mean() ** 0.5),
                    "me_uncorrected": float((g["uncorrected"] - g["points"]).mean()),
                    "me_corrected": float((g["corrected"] - g["points"]).mean()),
                    "t_corrected_vs_uncorrected": oh.weekly_t(g, "corrected", "uncorrected"),
                }
            )
        print(f"\n{name}, 2026 weeks 1-6")
        print(pl.DataFrame(out))


if __name__ == "__main__":
    main()
