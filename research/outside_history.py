"""FFToday's served past-week projections: are they re-stamped after the games, and how do they
compare with ours?

1. Backfill (one time, cached): FFToday weekly pages for SEASONS x weeks 1 to 6 x QB, RB, WR, TE,
   first page only (top 50 by FFToday's points), PAUSE seconds apart, under research/scratch/fftoday
   (gitignored). Pages already cached are not fetched again.
2. Re-stamp check. Sleeper's past weeks are re-stamped: players who sat got about 1.3 points against
   8.2 for those who played. Here, per status on the nflverse game-week injury report, the mean
   FFToday projection (Colgate scoring) for players with and without a stat line that week. A clean
   pre-game source gives a Questionable player who then sat about what it gives one who played.
3. History test, rows where all exist (FFToday mapped to gsis_id, our walk-forward learned
   projection from proj_learned, a stat line): RMSE and MAE by position for ours, FFToday and the
   equal-weight mean, paired weekly t on squared error (mean minus ours). Report only.

Sleeper's history is re-stamped, so no ours + FFToday + Sleeper mean is scored here; FantasySharks
is not used (its terms forbid robots). Rows are FFToday's top 50 per position and players with a
stat line, so a source that drops players who sat cannot bias the comparison.

Run from the repo root: uv run python research/outside_history.py [season ...]  (default 2026)
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
import polars as pl

from fantasy import store
from fantasy.stages import outside_projections as op
from fantasy.stages.sleeper_projections import score_stats

CACHE = Path("research/scratch/fftoday")
SEASONS = tuple(int(s) for s in sys.argv[1:]) or (2026,)
WEEKS = range(1, 7)
PAUSE = 5.0
pl.Config(tbl_rows=60, tbl_cols=14, tbl_width_chars=180, float_precision=3)


def backfill() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    for season in SEASONS:
        for week in WEEKS:
            for pos in op.POSITIONS:
                path = CACHE / f"{season}_{week}_{op.FFTODAY_POS_ID[pos]}.html"
                if path.exists() and path.stat().st_size:
                    continue
                path.write_text(op.fetch_fftoday(season, week, pos))
                print(f"fetched {path}")
                time.sleep(PAUSE)


def fftoday_rows() -> pl.DataFrame:
    rows = []
    for season in SEASONS:
        for week in WEEKS:
            for pos in op.POSITIONS:
                page = (CACHE / f"{season}_{week}_{op.FFTODAY_POS_ID[pos]}.html").read_text()
                rows += [
                    {"season": season, "week": week, "position": pos, **r, "stats": json.dumps(r["stats"])}
                    for r in op.parse_fftoday(page, pos)
                ]
    return pl.DataFrame(rows)


def scored(snaps: pl.DataFrame, scoring: dict[str, float]) -> pl.DataFrame:
    return snaps.with_columns(
        pl.Series("fftoday", [score_stats(json.loads(s), scoring) for s in snaps["stats"]], dtype=pl.Float64)
    )


def restamp_check(snaps: pl.DataFrame, league_id: str) -> None:
    played = (
        store.read_table("player_points")
        .filter(pl.col("league_id") == league_id)
        .select("gsis_id", "season", "week", pl.lit(True).alias("played"))
    )
    status = (
        store.read_table("nfl_injuries", "raw")
        .filter(pl.col("game_type") == "REG")
        .select("gsis_id", "season", "week", pl.col("report_status").alias("status"))
        .unique(["gsis_id", "season", "week"], keep="first")
    )
    d = (
        snaps.join(played, on=["gsis_id", "season", "week"], how="left")
        .join(status, on=["gsis_id", "season", "week"], how="left")
        .with_columns(pl.col("played").fill_null(False), pl.col("status").fill_null("none"))
    )
    print("\nRe-stamp check: mean FFToday projection by report status and whether the player had a stat line")
    print(
        d.group_by("season", "status", "played")
        .agg(pl.len().alias("n"), pl.col("fftoday").mean().alias("mean_proj"), (pl.col("fftoday") < 1).sum().alias("under_1"))
        .sort("season", "status", "played")
    )
    # players listed Out who were in FFToday's list the week before: still listed?
    prior = snaps.select("gsis_id", "season", (pl.col("week") + 1).alias("week")).unique()
    out = status.filter(pl.col("status") == "Out").join(prior, on=["gsis_id", "season", "week"], how="semi")
    listed = out.join(snaps.select("gsis_id", "season", "week"), on=["gsis_id", "season", "week"], how="semi")
    print(f"Out-listed players who were in last week's list: {out.height}, still listed this week: {listed.height}")
    if listed.height:
        print(listed.join(snaps, on=["gsis_id", "season", "week"]).select("season", "week", "name", "position", "fftoday").sort("fftoday", descending=True).head(10))


def weekly_t(d: pl.DataFrame, a: str, b: str) -> float:
    w = d.group_by("season", "week").agg(((pl.col(a) - pl.col("points")) ** 2 - (pl.col(b) - pl.col("points")) ** 2).mean().alias("x"))
    x = w["x"].to_numpy()
    return float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) > 0 else float("nan")


def history_test(snaps: pl.DataFrame, league_id: str) -> None:
    ours = (
        store.read_table("proj_learned")
        .filter((pl.col("league_id") == league_id) & ~pl.col("is_future") & pl.col("season").is_in(list(SEASONS)))
        .select("gsis_id", "season", "week", "as_of_week", pl.col("projection").alias("ours"))
    )
    points = store.read_table("player_points").filter(pl.col("league_id") == league_id).select("gsis_id", "season", "week", "points")
    d = (
        snaps.drop_nulls("gsis_id")
        .select("gsis_id", "season", "week", "position", "fftoday")
        .join(ours, on=["gsis_id", "season", "week"])
        .join(points, on=["gsis_id", "season", "week"])
        .with_columns(((pl.col("ours") + pl.col("fftoday")) / 2).alias("mean_eq"))
    )
    lag = (d["week"] - d["as_of_week"]).value_counts()
    print(f"rows with all three: {d.height}; week - as_of_week: {dict(lag.iter_rows())}")
    out = []
    for pos in [None, *op.POSITIONS]:
        g = d if pos is None else d.filter(pl.col("position") == pos)
        row: dict[str, object] = {"position": pos or "ALL", "n": g.height}
        for c in ("ours", "fftoday", "mean_eq"):
            row[f"rmse_{c}"] = float(((g[c] - g["points"]) ** 2).mean() ** 0.5)
            row[f"mae_{c}"] = float((g[c] - g["points"]).abs().mean())
            row[f"me_{c}"] = float((g[c] - g["points"]).mean())
        row["t_ff_vs_ours"] = weekly_t(g, "fftoday", "ours")
        row["t_mean_vs_ours"] = weekly_t(g, "mean_eq", "ours")
        out.append(row)
    print(pl.DataFrame(out))
    print("t < 0 means the first projection has the lower squared error (weekly paired, weeks - 1 df)")


def main() -> None:
    backfill()
    raw = fftoday_rows()
    mapped = op.map_to_gsis(raw, op.people())
    print(f"FFToday rows {raw.height}, mapped to gsis_id {mapped['gsis_id'].is_not_null().mean():.1%}")
    for league in store.read_table("leagues", "raw").iter_rows(named=True):
        print(f"\n===== {league['name']}")
        snaps = scored(mapped.drop_nulls("gsis_id"), json.loads(league["scoring_settings"]))
        if league["league_id"] == "1394105943137992704":
            restamp_check(snaps, league["league_id"])
        history_test(snaps, league["league_id"])


if __name__ == "__main__":
    main()
