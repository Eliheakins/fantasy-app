"""Is the learned projection biased upward, why, and does a walk-forward recalibration help?

Uses the walk-forward history already in `proj_learned` (seasons 2021 on; 2019 and 2020 were
scored by models that saw later seasons and are never used) and `proj_baseline`.

1. Mean error (projection minus actual) by season, position, size tier, week bucket,
   has_history, and 2026 weeks 1-6, on the held-out protocol rows of `learn.compare_to_baseline`
   (has_history, size-calibrated baseline above 3 points), per league.
2. Training filter: skill player-games with offensive snaps but no `player_points` row (no stat
   line). Both training and the scorecard drop them; their size and the bias they would add.
3. Scale drift: points per player-game, weeks 1-6, 2026 against 2021-2025.
4. Week 7 rows in this data copy (reported, not used).
5. Recalibration candidates per position, fit walk-forward on earlier seasons' learned history
   (2021..s-1), scored on 2024, 2025 and 2026: an intercept shift, linear a + b * projection, and
   isotonic. Paired per-week t against the current learned model, weeks better, per season, and a
   sign test over league-season-position cells.

Run from the repo root: OMP_NUM_THREADS=3 uv run python research/bias_check.py
"""

from math import comb

import numpy as np
import polars as pl
from sklearn.isotonic import IsotonicRegression

from fantasy import store
from fantasy.sim.calibration import apply_curves
from fantasy.stages.backtest import size_tiers
from fantasy.stages.distributions import estimate_curves, residual_frame
from fantasy.stages.learn import MIN_PROJECTION

FIRST_CLEAN = 2021  # learned history before this saw later seasons
FIRST_SCORED = 2024
SKILL = ["QB", "RB", "WR", "TE"]
KEYS = ["league_id", "gsis_id", "season", "week"]
pl.Config(tbl_rows=60, tbl_cols=14, tbl_width_chars=180, float_precision=3)


def league_names() -> dict[str, str]:
    lg = store.read_table("leagues", "raw")
    return {r["league_id"]: r["name"].split()[0] for r in lg.iter_rows(named=True)}


def protocol_rows() -> pl.DataFrame:
    """Past games from 2021 on with learned, raw baseline, size-calibrated baseline (curves from
    earlier seasons only) and points. `protocol` marks the compare_to_baseline rows."""
    baseline = store.read_table("proj_baseline").filter(~pl.col("is_future"))
    learned = store.read_table("proj_learned").filter(~pl.col("is_future"))
    points = store.read_table("player_points")
    history = residual_frame(baseline, points)
    parts = []
    for (league_id,), lb in baseline.group_by("league_id"):
        for season in sorted(s for s in lb["season"].unique().to_list() if s >= FIRST_CLEAN):
            curves = estimate_curves(
                history.filter((pl.col("league_id") == league_id) & (pl.col("season") < season))
            )
            raw = lb.filter(pl.col("season") == season)
            cal = apply_curves(raw, curves).select(*KEYS, pl.col("projection").alias("base_cal"))
            parts.append(
                raw.select(*KEYS, "position", "has_history", pl.col("projection").alias("base"))
                .join(cal, on=KEYS)
                .join(learned.select(*KEYS, pl.col("projection").alias("learned")), on=KEYS)
                .join(points.select(*KEYS, "points"), on=KEYS)
            )
    return pl.concat(parts).with_columns(
        protocol=pl.col("has_history") & (pl.col("base_cal") > MIN_PROJECTION),
        wk_bucket=pl.when(pl.col("week") <= 4)
        .then(pl.lit("01-04"))
        .when(pl.col("week") <= 9)
        .then(pl.lit("05-09"))
        .otherwise(pl.lit("10-18+")),
    )


def with_tiers(rows: pl.DataFrame) -> pl.DataFrame:
    """Learned projection thirds per league and position, edges from 2021-2023 learned rows."""
    parts = []
    for (lid, pos), g in rows.group_by("league_id", "position"):
        train = g.filter(pl.col("season") < FIRST_SCORED)["learned"].to_numpy()
        parts.append(g.with_columns(pl.Series("tier", size_tiers(train, g["learned"].to_numpy()))))
    return pl.concat(parts)


def bias_by(rows: pl.DataFrame, by: list[str]) -> pl.DataFrame:
    return (
        rows.group_by(["league", *by])
        .agg(
            pl.len().alias("n"),
            (pl.col("learned") - pl.col("points")).mean().alias("me_learned"),
            (pl.col("base") - pl.col("points")).mean().alias("me_base"),
            (pl.col("base_cal") - pl.col("points")).mean().alias("me_base_cal"),
            ((pl.col("learned") - pl.col("points")).std() / pl.len().sqrt()).alias("se_learned"),
            pl.col("points").mean().alias("pts"),
        )
        .sort(["league", *by])
    )


def part1(rows: pl.DataFrame) -> None:
    print("\n== 1. Mean error (projection minus actual), protocol rows, 2021 on ==")
    p = rows.filter(pl.col("protocol"))
    for by in (["season"], ["position", "season"], ["tier", "season"], ["wk_bucket"]):
        print(bias_by(p.filter(pl.col("season") >= 2021), by))
    print("has_history (all rows, no size filter):")
    print(bias_by(rows, ["has_history"]))
    print("2026 weeks 1-6 by position:")
    print(bias_by(p.filter((pl.col("season") == 2026) & (pl.col("week") <= 6)), ["position"]))
    print("2026 weeks 1-6 by week:")
    print(bias_by(p.filter((pl.col("season") == 2026) & (pl.col("week") <= 6)), ["week"]))


def snap_games() -> pl.DataFrame:
    snaps = store.read_table("nfl_snaps", "raw").filter(
        pl.col("gsis_id").is_not_null()
        & pl.col("position").is_in(SKILL)
        & (pl.col("offense_snaps") > 0)
        & (pl.col("season") >= FIRST_CLEAN)
    )
    return snaps.select("gsis_id", "season", "week", "position", "offense_snaps").unique(
        ["gsis_id", "season", "week"]
    )


def part2(rows: pl.DataFrame) -> None:
    print("\n== 2. Player-games with offensive snaps but no player_points row ==")
    pts = store.read_table("player_points")
    learned = store.read_table("proj_learned").filter(~pl.col("is_future"))
    snaps = snap_games()
    for lid, name in league_names().items():
        have = pts.filter(pl.col("league_id") == lid).select("gsis_id", "season", "week")
        flagged = snaps.join(have, on=["gsis_id", "season", "week"], how="anti")
        share = (
            snaps.with_columns(
                missing=pl.struct("gsis_id", "season", "week").is_in(
                    flagged.select(pl.struct("gsis_id", "season", "week")).to_series().implode()
                )
            )
            .group_by("position")
            .agg(
                pl.len().alias("snap_games"),
                pl.col("missing").sum().alias("no_statline"),
                pl.col("missing").mean().alias("share"),
                pl.col("offense_snaps").filter(pl.col("missing")).median().alias("med_snaps"),
            )
            .sort("position")
        )
        print(f"{name}:")
        print(share)
        # what the model would have said: the player's previous projected game, as a stand-in
        prev = (
            learned.filter((pl.col("league_id") == lid) & (pl.col("season") >= FIRST_CLEAN))
            .select("gsis_id", (store.week_index()).alias("t"), "projection")
            .sort("t")
        )
        stand_in = (
            flagged.with_columns(store.week_index().alias("t"))
            .sort("t")
            .join_asof(prev, on="t", by="gsis_id", strategy="backward", allow_exact_matches=False)
        )
        print(
            "  stand-in projection (previous projected game) for no-statline games: "
            f"mean {stand_in['projection'].mean():.2f}, share above 3 points "
            f"{(stand_in['projection'] > MIN_PROJECTION).mean():.3f}, "
            f"n with a prior projection {stand_in['projection'].is_not_null().sum()}"
        )
        # share of snap games without a stat line, by the player's previous projection: what the
        # simulation over-counts when it treats "plays" (any snaps) as earning E[points | stat line]
        every = (
            snaps.with_columns(store.week_index().alias("t"))
            .sort("t")
            .join_asof(prev, on="t", by="gsis_id", strategy="backward", allow_exact_matches=False)
            .join(have.with_columns(pl.lit(True).alias("statline")), on=["gsis_id", "season", "week"], how="left")
            .with_columns(
                pl.col("statline").fill_null(False),
                band=pl.when(pl.col("projection") > 8)
                .then(pl.lit("prev>8"))
                .when(pl.col("projection") > 3)
                .then(pl.lit("prev3-8"))
                .otherwise(pl.lit("prev<=3/none")),
            )
        )
        print(
            every.group_by("position", "band")
            .agg(
                pl.len().alias("snap_games"),
                (~pl.col("statline")).mean().alias("share_no_statline"),
                pl.col("projection").filter(~pl.col("statline")).mean().alias("prev_proj_missing"),
            )
            .sort("position", "band")
        )
        # bias the protocol scorecard would show if those games were scored as 0
        lp = rows.filter((pl.col("league_id") == lid) & pl.col("protocol"))
        extra = stand_in.filter(pl.col("projection") > MIN_PROJECTION)
        n0, s0 = lp.height, float((lp["learned"] - lp["points"]).sum())
        added = float(extra["projection"].sum())
        print(
            f"  protocol mean error {s0 / n0:+.3f} on {n0} rows; with {extra.height} no-statline "
            f"games at 0 points (stand-in projection above 3): {(s0 + added) / (n0 + extra.height):+.3f}"
        )
    print(
        "Training (expected_frame inner-joins player_points) and the scorecard (score_games marks "
        "a game with no points row not_final) both drop these games."
    )


def part3() -> None:
    print("\n== 3. Scale drift: points per player-game, weeks 1-6, skill positions ==")
    pts = store.read_table("player_points").filter(
        (pl.col("season") >= FIRST_CLEAN) & (pl.col("week") <= 6) & pl.col("position").is_in(SKILL)
    )
    names = league_names()
    table = (
        pts.with_columns(pl.col("league_id").replace_strict(names).alias("league"))
        .with_columns(era=pl.when(pl.col("season") == 2026).then(pl.lit("2026")).otherwise(pl.lit("21-25")))
        .group_by("league", "position", "era")
        .agg(pl.col("points").mean().alias("pts"), pl.len().alias("n"))
        .pivot(on="era", index=["league", "position"], values=["pts", "n"])
        .sort("league", "position")
    )
    print(table.with_columns((pl.col("pts_2026") - pl.col("pts_21-25")).alias("diff")))
    print("by season (all skill positions, weeks 1-6):")
    print(
        pts.with_columns(pl.col("league_id").replace_strict(names).alias("league"))
        .group_by("league", "season")
        .agg(pl.col("points").mean().alias("pts"), pl.len().alias("n"))
        .sort("league", "season")
    )


def part4(rows: pl.DataFrame) -> None:
    print("\n== 4. Week 7 of 2026 in this data copy (walk-forward history rows, not snapshots) ==")
    w7 = rows.filter((pl.col("season") == 2026) & (pl.col("week") == 7))
    print(bias_by(w7, ["protocol"]))


# ---------- 5. recalibration ----------


def fit_map(kind: str, x: np.ndarray, y: np.ndarray):  # noqa: ANN201
    if kind == "shift":
        c = float((y - x).mean())
        return lambda z: np.clip(z + c, 0, None)
    if kind == "linear":
        b, a = np.polyfit(x, y, 1)
        return lambda z: np.clip(a + b * z, 0, None)
    iso = IsotonicRegression(out_of_bounds="clip").fit(x, y)
    return lambda z: iso.predict(z)


def recalibrated(rows: pl.DataFrame, kind: str, fit_rows: pl.DataFrame | None = None) -> pl.DataFrame:
    """Protocol rows of 2024 on, with `recal`: the per-league-position map fit on protocol rows
    of 2021..s-1 (or of `fit_rows`, for the placebo)."""
    source = rows if fit_rows is None else fit_rows
    parts = []
    for (lid, pos, season), g in rows.filter(pl.col("season") >= FIRST_SCORED).group_by(
        "league_id", "position", "season"
    ):
        train = source.filter(
            (pl.col("league_id") == lid)
            & (pl.col("position") == pos)
            & (pl.col("season") < season)
            & (pl.col("season") >= FIRST_CLEAN)
        )
        f = fit_map(kind, train["learned"].to_numpy(), train["points"].to_numpy())
        parts.append(g.with_columns(pl.Series("recal", f(g["learned"].to_numpy()))))
    return pl.concat(parts)


def score(d: pl.DataFrame) -> dict[str, float | str]:
    by_week = d.group_by("season", "week").agg(
        ((pl.col("learned") - pl.col("points")) ** 2).mean().alias("a"),
        ((pl.col("recal") - pl.col("points")) ** 2).mean().alias("b"),
    )
    diff = (by_week["a"] - by_week["b"]).to_numpy()
    se_a = float(((d["learned"] - d["points"]) ** 2).mean())
    se_b = float(((d["recal"] - d["points"]) ** 2).mean())
    t = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))) if len(diff) > 2 else float("nan")
    return {
        "n": d.height,
        "rmse_learned": round(se_a**0.5, 4),
        "rmse_recal": round(se_b**0.5, 4),
        "gain_pct": round(100 * (se_a**0.5 - se_b**0.5) / se_a**0.5, 3),
        "mae_learned": round(float((d["learned"] - d["points"]).abs().mean()), 4),
        "mae_recal": round(float((d["recal"] - d["points"]).abs().mean()), 4),
        "me_learned": round(float((d["learned"] - d["points"]).mean()), 3),
        "me_recal": round(float((d["recal"] - d["points"]).mean()), 3),
        "t": round(t, 2),
        "weeks_better": f"{int((diff > 0).sum())}/{len(diff)}",
    }


def sign_test(wins: int, n: int) -> float:
    """Two-sided binomial p for `wins` of `n` at 0.5."""
    k = min(wins, n - wins)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2**n)


def part5(rows: pl.DataFrame) -> None:
    print("\n== 5. Recalibration of the learned projection, fit 2021..s-1, scored 2024 on ==")
    p = rows.filter(pl.col("protocol") & (pl.col("season") >= FIRST_CLEAN))
    rng = np.random.default_rng(0)
    # placebo: earlier-season labels shuffled among 2021..2025 rows, so a fit sees a random
    # mixture of seasons (it may include later seasons; a gain here means the map is not
    # about a season trend)
    seasons = p["season"].to_numpy().copy()
    early = seasons < 2026
    seasons[early] = rng.permutation(seasons[early])
    placebo_fit = p.with_columns(pl.Series("season", seasons))
    for kind in ("shift", "linear", "isotonic", "linear_placebo"):
        real = kind.removesuffix("_placebo")
        d = recalibrated(p, real, placebo_fit if kind.endswith("placebo") else None)
        out = []
        for (lid,), g in d.group_by("league"):
            out.append({"league": lid, "season": "all", **score(g)})
            for (s,), gs in g.group_by("season"):
                out.append({"league": lid, "season": str(s), **score(gs)})
        print(f"-- {kind}")
        print(pl.DataFrame(out).sort("league", "season"))
        if kind == "linear_placebo":
            continue
        cells = (
            d.group_by("league", "season", "position")
            .agg(
                ((pl.col("learned") - pl.col("points")) ** 2).mean().alias("a"),
                ((pl.col("recal") - pl.col("points")) ** 2).mean().alias("b"),
            )
            .with_columns((pl.col("b") < pl.col("a")).alias("better"))
        )
        wins = int(cells["better"].sum())
        print(
            f"   sign test, league-season-position cells better: {wins}/{cells.height}, "
            f"p = {sign_test(wins, cells.height):.3f}"
        )
        pos = d.group_by("league", "position").agg(
            ((pl.col("learned") - pl.col("points")) ** 2).mean().sqrt().alias("rmse_learned"),
            ((pl.col("recal") - pl.col("points")) ** 2).mean().sqrt().alias("rmse_recal"),
            (pl.col("learned") - pl.col("points")).mean().alias("me_learned"),
            (pl.col("recal") - pl.col("points")).mean().alias("me_recal"),
        )
        print(pos.sort("league", "position"))


def main() -> None:
    names = league_names()
    rows = with_tiers(protocol_rows()).with_columns(
        pl.col("league_id").replace_strict(names).alias("league")
    )
    part1(rows)
    part2(rows)
    part3()
    part4(rows)
    part5(rows)


if __name__ == "__main__":
    main()
