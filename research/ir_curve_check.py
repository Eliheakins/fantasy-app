"""IR return curve: how soon do players on injured reserve play again?

Production (`sim/injuries.py`, `sim/odds.py`) gives an IR player 0 for his next four team games,
then the general absence chain (out after out 55%, out after playing 7%), so from his sixth game
on he reads 67% to 86% available, season-ending injuries included. Here the chance of playing
each later team game is measured instead.

Population: every regular-season week a skill player is on injured reserve in nflverse weekly
rosters (status RES with Reserve/Injured codes R01 or R48; 2018 and 2019, and part of 2020, have
no code, so every RES row counts), if he had 5 or more touches or targets in a game earlier that
season or the season before. Each such week is scored for his team's games k = 0, 1, ... to the
end of the regular season (k = 0 is that week's game; byes do not count), as production applies
the curve every week he is listed. Played: any touch or target (`nfl_player_stats`), the event the
injury table measures.

Curves, fit on 2018 to 2023, scored on 2024 and 2025 (Brier, log loss):
  current   0 for k < 4, then the chain from out.
  fitted    the share who played at each k (primary, fixed before the run), made non-decreasing.
  by_time   the same by games already on IR this season (0, 1 to 3, 4 or more), shrunk to the
            primary with 30 pseudo-rows (production cannot see this today).
  by_body   by the body part of his last injury report that season, shrunk the same way.
  fit21     the primary fit on 2021 to 2023 only (the four-game minimum and more returns).
Paired bootstrap over player-seasons (2,000 draws) of the Brier gain (current minus fitted) per
season. Ship rule (fixed before the run): the fitted curve ships if its Brier is lower in both 2024
and 2025 and each season's 95% bootstrap interval of the gain excludes 0.

Secondary: players listed Out for the N-th team game in a row (N >= 2), against the injury table's
Out curve (refit on 2018 to 2023) followed by the chain; by_streak rates by k and N.

The weekly roster status is not in `data/raw` (ingest keeps age and experience only), so the first
run downloads nflverse weekly rosters (public, via nflreadpy) into `research/scratch/`.

Run from the repo root:  OMP_NUM_THREADS=3 uv run python research/ir_curve_check.py
"""

from pathlib import Path

import numpy as np
import polars as pl

from fantasy import store
from fantasy.sim.injuries import InjuryModel
from fantasy.sim.odds import HAZARD, STAY_OUT
from fantasy.stages import injuries as inj

ROSTERS = Path(__file__).parent / "scratch" / "nflverse_rosters_weekly.parquet"
IR_CODES = ("R01", "R48")
POSITIONS = ("QB", "RB", "WR", "TE")
FIT = (2018, 2023)
FIT_RECENT = (2021, 2023)
TEST = (2024, 2025)
HORIZON = 18  # team games ahead, enough for a whole regular season
MIN_WEEKS = 4  # production's zero games for IR
SHRINK = 30.0
CLIP = 1e-3  # for log loss
BOOT = 2000
BODIES = ("Knee", "Ankle", "Hamstring", "Foot", "Shoulder", "Achilles")
KEY3 = ["gsis_id", "season", "week"]


# ---------------------------------------------------------------- data


def weekly_rosters() -> pl.DataFrame:
    if not ROSTERS.exists():
        import nflreadpy as nfl

        ROSTERS.parent.mkdir(exist_ok=True)
        nfl.load_rosters_weekly(list(range(2018, 2027))).write_parquet(ROSTERS)
    return pl.read_parquet(ROSTERS).with_columns(pl.col("season", "week").cast(pl.Int64))


def touches() -> pl.DataFrame:
    """gsis_id, season, week, opp (touches plus targets) for regular-season stat rows."""
    stats = store.read_table("nfl_player_stats", "raw").filter(pl.col("season_type") == "REG")
    opp = (
        pl.col("attempts").fill_null(0)
        + pl.col("carries").fill_null(0)
        + pl.col("targets").fill_null(0)
    )
    return stats.select(pl.col("player_id").alias("gsis_id"), "season", "week", opp.alias("opp"))


def relevant(rows: pl.DataFrame, opp: pl.DataFrame) -> pl.DataFrame:
    """Rows of players with 5 or more touches or targets in a game earlier that season or in the
    season before."""
    busy = opp.filter(pl.col("opp") >= 5).select("gsis_id", "season", "week")
    same = rows.join(busy, on=["gsis_id", "season"], suffix="_b").filter(
        pl.col("week_b") < pl.col("week")
    )
    prior = rows.join(
        busy.with_columns(pl.col("season") + 1).select("gsis_id", "season").unique(),
        on=["gsis_id", "season"],
    )
    keep = pl.concat([same.select(KEY3), prior.select(KEY3)]).unique()
    return rows.join(keep, on=KEY3, how="semi")


def horizons(rows: pl.DataFrame, opp: pl.DataFrame) -> pl.DataFrame:
    """One row per listed player-week and later team game k: played (bool)."""
    games = store.team_game_index(store.read_table("team_games"))
    base = rows.join(games, on=["team", "season", "week"])
    later = base.join(
        games.select("team", "season", pl.col("g").alias("g2"), pl.col("week").alias("wk")),
        on=["team", "season"],
    ).filter((pl.col("g2") >= pl.col("g")) & (pl.col("g2") < pl.col("g") + HORIZON))
    played = opp.filter(pl.col("opp") > 0).select(
        "gsis_id", "season", pl.col("week").alias("wk"), pl.lit(True).alias("played")
    )
    return (
        later.join(played, on=["gsis_id", "season", "wk"], how="left")
        .with_columns(
            (pl.col("g2") - pl.col("g")).alias("k"),
            pl.col("played").fill_null(False).cast(pl.Float64),
        )
        .drop("g2", "wk")
    )


def ir_rows(rosters: pl.DataFrame, opp: pl.DataFrame) -> pl.DataFrame:
    """IR player-weeks with games already on IR this season and the last reported body part."""
    code = pl.col("status_description_abbr")
    rows = (
        rosters.filter(
            (pl.col("game_type") == "REG")
            & pl.col("position").is_in(POSITIONS)
            & (pl.col("status") == "RES")
            & (code.is_in(IR_CODES) | code.is_null())
            & pl.col("gsis_id").is_not_null()
        )
        .select(*KEY3, "team")
        .unique(KEY3)
        .sort(KEY3)
        .with_columns(pl.int_range(pl.len()).over("gsis_id", "season").alias("on_ir"))
    )
    rows = relevant(rows, opp)
    reports = (
        store.read_table("nfl_injuries", "raw")
        .filter(pl.col("game_type") == "REG")
        .select(
            "gsis_id",
            "season",
            pl.col("week").alias("rw"),
            pl.coalesce("report_primary_injury", "practice_primary_injury").alias("body"),
        )
        .drop_nulls("body")
        .sort("rw")
    )
    rows = rows.sort("week").join_asof(
        reports, left_on="week", right_on="rw", by=["gsis_id", "season"], strategy="backward"
    )
    return rows.with_columns(
        pl.when(pl.col("body").is_in(BODIES)).then("body").otherwise(pl.lit("Other")),
        pl.when(pl.col("on_ir") == 0)
        .then(pl.lit("0"))
        .when(pl.col("on_ir") < MIN_WEEKS)
        .then(pl.lit("1-3"))
        .otherwise(pl.lit("4+"))
        .alias("time"),
    ).drop("rw")


# ---------------------------------------------------------------- curves


def chain_after(curve: list[float], n: int) -> np.ndarray:
    """`curve` (chance of playing) for its games, then the production chain to n games."""
    out = [1.0 - p for p in curve[:n]]
    while len(out) < n:
        q = out[-1]
        out.append(q * STAY_OUT + (1.0 - q) * HAZARD)
    return 1.0 - np.array(out)


def current_ir() -> np.ndarray:
    return chain_after([0.0] * MIN_WEEKS, HORIZON)


def rate_by_k(panel: pl.DataFrame) -> np.ndarray:
    rates = panel.group_by("k").agg(pl.col("played").mean()).sort("k")
    by_k = dict(zip(rates["k"], rates["played"], strict=True))
    out = np.array([by_k.get(k, np.nan) for k in range(HORIZON)])
    out = pl.Series(out).fill_nan(None).forward_fill().to_numpy()  # unseen tail keeps the last
    return np.maximum.accumulate(out)


def grouped(panel: pl.DataFrame, column: str, pooled: np.ndarray) -> dict[str, np.ndarray]:
    """Per value of `column`, rates by k shrunk toward `pooled`, made non-decreasing."""
    out = {}
    for (value,), g in panel.group_by(column):
        stats = g.group_by("k").agg(pl.col("played").sum().alias("s"), pl.len().alias("n"))
        s = dict(zip(stats["k"], stats["s"], strict=True))
        n = dict(zip(stats["k"], stats["n"], strict=True))
        curve = np.array(
            [(s.get(k, 0) + SHRINK * pooled[k]) / (n.get(k, 0) + SHRINK) for k in range(HORIZON)]
        )
        out[str(value)] = np.maximum.accumulate(curve)
    return out


def in_years(frame: pl.DataFrame, years: tuple[int, int]) -> pl.DataFrame:
    return frame.filter(pl.col("season").is_between(*years))


# ---------------------------------------------------------------- scoring


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    q = np.clip(p, CLIP, 1 - CLIP)
    return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))


def bootstrap_gain(test: pl.DataFrame, base: str, cand: str, seed: int = 0) -> tuple[float, float]:
    """95% interval of mean(base Brier - cand Brier), resampling player-seasons."""
    per = (
        test.with_columns(
            ((pl.col(base) - pl.col("played")) ** 2 - (pl.col(cand) - pl.col("played")) ** 2).alias(
                "d"
            )
        )
        .group_by("gsis_id", "season")
        .agg(pl.col("d").sum(), pl.len().alias("n"))
    )
    d, n = per["d"].to_numpy(), per["n"].to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(d), size=(BOOT, len(d)))
    gains = d[idx].sum(axis=1) / n[idx].sum(axis=1)
    lo, hi = np.quantile(gains, [0.025, 0.975])
    return float(lo), float(hi)


def score_table(test: pl.DataFrame, cols: list[str], base: str = "current") -> pl.DataFrame:
    rows = []
    for (season,), g in sorted(test.group_by("season"), key=lambda t: t[0]):
        y = g["played"].to_numpy()
        for c in cols:
            lo, hi = bootstrap_gain(g, base, c) if c != base else (0.0, 0.0)
            rows.append(
                {
                    "season": season,
                    "curve": c,
                    "rows": g.height,
                    "players": g.select("gsis_id").n_unique(),
                    "played": round(float(y.mean()), 4),
                    "mean_p": round(float(g[c].mean()), 4),
                    "brier": round(brier(g[c].to_numpy(), y), 4),
                    "log_loss": round(log_loss(g[c].to_numpy(), y), 4),
                    "gain_lo": round(lo, 4),
                    "gain_hi": round(hi, 4),
                }
            )
    return pl.DataFrame(rows)


def attach(test: pl.DataFrame, name: str, curve: np.ndarray) -> pl.DataFrame:
    return test.with_columns(pl.col("k").map_elements(lambda k: float(curve[k])).alias(name))


def attach_grouped(
    test: pl.DataFrame, name: str, column: str, curves: dict[str, np.ndarray], pooled: np.ndarray
) -> pl.DataFrame:
    values = [
        float(curves.get(str(v), pooled)[k]) for v, k in zip(test[column], test["k"], strict=True)
    ]
    return test.with_columns(pl.Series(name, values))


# ---------------------------------------------------------------- Out streaks (secondary)


def out_streaks(opp: pl.DataFrame) -> pl.DataFrame:
    """Out player-weeks with N, the count of consecutive team games he has been listed Out."""
    games = store.team_game_index(store.read_table("team_games"))
    out = (
        store.read_table("nfl_injuries", "raw")
        .filter(
            (pl.col("game_type") == "REG")
            & (pl.col("report_status") == "Out")
            & pl.col("position").is_in(POSITIONS)
        )
        .unique(KEY3)
        .select(*KEY3, "team", pl.coalesce("report_primary_injury", "practice_primary_injury"))
        .rename({"report_primary_injury": "body"})
        .join(games, on=["team", "season", "week"])
        .sort("gsis_id", "season", "g")
    )
    run_id = (pl.col("g").diff().over("gsis_id", "season").fill_null(1) != 1).cum_sum()
    out = out.with_columns(run_id.over("gsis_id", "season").alias("_run"))
    out = out.with_columns(
        (pl.int_range(pl.len()).over("gsis_id", "season", "_run") + 1).alias("streak")
    ).drop("_run", "g")
    return relevant(out, opp)


def out_table_curve(opp: pl.DataFrame) -> dict[str, np.ndarray]:
    """The injury table's Out curve by body (fit on 2018 to 2023), followed by the chain."""
    empty_points = pl.DataFrame(
        schema={"gsis_id": pl.String, "season": pl.Int64, "week": pl.Int64, "points": pl.Float64}
    )
    empty_proj = empty_points.rename({"points": "proj"})
    panel = inj.build_panel(
        in_years(store.read_table("nfl_injuries", "raw"), FIT),
        store.read_table("nfl_player_stats", "raw"),
        store.read_table("team_games"),
        empty_points,
        empty_proj,
    )
    model = InjuryModel(inj.estimate(panel))
    out = {}
    for body in (*inj.BODIES, inj.OTHER):
        curve = model.curve(("Out", body, None))
        assert curve is not None
        out[body] = chain_after(list(curve[0][:-1]), HORIZON)
    return out


def streak_check(opp: pl.DataFrame) -> pl.DataFrame:
    rows = out_streaks(opp).filter(pl.col("streak") >= 2)
    panel = horizons(rows, opp).with_columns(
        pl.when(pl.col("body").is_in(inj.BODIES)).then("body").otherwise(pl.lit(inj.OTHER)),
        pl.when(pl.col("streak") <= 3)
        .then(pl.lit("2-3"))
        .otherwise(pl.lit("4+"))
        .alias("streak_group"),
    )
    table = out_table_curve(opp)
    pooled = rate_by_k(in_years(panel, FIT))
    by_streak = grouped(in_years(panel, FIT), "streak_group", pooled)
    test = in_years(panel, TEST)
    test = attach_grouped(test, "current", "body", table, table[inj.OTHER])
    test = attach(test, "fitted", pooled)
    test = attach_grouped(test, "by_streak", "streak_group", by_streak, pooled)
    return score_table(test, ["current", "fitted", "by_streak"])


# ---------------------------------------------------------------- main


def self_check() -> None:
    cur = current_ir()
    assert cur[:MIN_WEEKS].max() == 0.0 and abs(cur[MIN_WEEKS] - (1 - STAY_OUT)) < 1e-12
    assert 0.85 < cur[-1] < 0.87  # the chain's resting availability
    toy = pl.DataFrame({"k": [0, 0, 1, 1, 3], "played": [0.0, 1.0, 0.0, 0.0, 1.0]})
    np.testing.assert_allclose(rate_by_k(toy)[:5], [0.5, 0.5, 0.5, 1.0, 1.0])


def main() -> None:
    self_check()
    opp = touches()
    rows = ir_rows(weekly_rosters(), opp)
    panel = horizons(rows, opp)
    print(f"IR player-weeks: {rows.height}, scored (week, k) pairs: {panel.height}")
    fit = in_years(panel, FIT)
    fitted = rate_by_k(fit)
    recent = rate_by_k(in_years(panel, FIT_RECENT))
    by_time = grouped(fit, "time", fitted)
    by_body = grouped(fit, "body", fitted)
    cur = current_ir()
    print("k, current, fitted 2018-23, fitted 2021-23, by time on IR (0 / 1-3 / 4+)")
    for k in range(HORIZON):
        times = " ".join(f"{by_time[t][k]:.3f}" for t in ("0", "1-3", "4+") if t in by_time)
        print(f"{k:2d}  {cur[k]:.3f}  {fitted[k]:.4f}  {recent[k]:.4f}  {times}")
    print("fitted curve tuple:", tuple(round(float(p), 4) for p in fitted))

    test = in_years(panel, TEST)
    test = attach(test, "current", cur)
    test = attach(test, "fitted", fitted)
    test = attach(test, "fit21", recent)
    test = attach_grouped(test, "by_time", "time", by_time, fitted)
    test = attach_grouped(test, "by_body", "body", by_body, fitted)
    table = score_table(test, ["current", "fitted", "fit21", "by_time", "by_body"])
    print("\nIR players' future games, held out (gain: current Brier minus the curve's, 95% CI)")
    print(table)
    primary = table.filter(pl.col("curve") == "fitted")
    current = table.filter(pl.col("curve") == "current")
    ships = bool((primary["brier"] < current["brier"]).all()) and bool(
        (primary["gain_lo"] > 0).all()
    )
    print(f"verdict fitted IR curve: {'SHIPS' if ships else 'no'}")

    print("\nSecondary: Out for the N-th game in a row (N >= 2), current = table curve + chain")
    print(streak_check(opp))


if __name__ == "__main__":
    pl.Config(tbl_rows=60, tbl_cols=20, tbl_width_chars=200)
    main()
