"""Follow-ups to hurdle_check.py once the two-part projection is in `learn`.

seeds   Protocol-row RMSE change of q * E against E (2024, 2025, 2026 weeks 1 to 6, REG) for six
        single classifier seeds and six disjoint three-seed bags. On protocol rows E is the
        switch-off `proj_learned` (OFF below); q comes from `stat_line.history_chance`.
shapes  Held-out spread shapes: `distributions.estimate_marginals` fit on 2021-2023 residuals,
        scored on 2024 on (2026 weeks 1 to 6), REG, projection above 0.5, tiers cut on the fit
        rows' projection as estimate_marginals cuts them. Mean pinball over the 99 levels
        (projection * ratio quantile) and 80% coverage, by league and tier, plus the mean ratio
        points / projection per tier on the fit rows. Arms:
          off       switch-off proj_learned (stat-line rows only), as production fits it now
          on        switch-on proj_learned: q * E on every active row (stat-less rows included)
          off_all   off shapes on every active row, E = on / q for the stat-less rows
          on_stat   on, scored on stat-line rows only
        Paired weekly t of on against off_all (same rows).

OFF: the switch-off proj_learned saved before the switch-on learn run. Run after
`stat_line_model = true` and `uv run python -m fantasy.stages.learn`:
  OMP_NUM_THREADS=3 uv run python research/hurdle_followup_check.py <off proj_learned parquet>
"""

import sys

import bias_check
import numpy as np
import polars as pl

from fantasy import store
from fantasy.stages import stat_line
from fantasy.stages.distributions import (
    LEVELS,
    MIN_PROJECTION,
    estimate_marginals,
    residual_frame,
    with_stat_line_flag,
)
from fantasy.stages.project import expected_frame

KEYS = ["league_id", "gsis_id", "season", "week"]
SCORED = (2024, 2025, 2026)
FIT = (2021, 2023)
LAST_2026_WEEK = 6
REG_LAST_WEEK = 18
pl.Config(tbl_rows=60, tbl_cols=14, tbl_width_chars=180, float_precision=4)


def scored_weeks() -> pl.Expr:
    return (pl.col("season") < 2026) | (pl.col("week") <= LAST_2026_WEEK)


def reg_keys() -> pl.DataFrame:
    pts = store.read_table("player_points")
    return pts.filter(pl.col("season_type") == "REG").select(KEYS)


def seeds_part(off: pl.DataFrame, names: dict[str, str]) -> None:
    leagues = store.read_table("leagues", "raw")
    points = store.read_table("player_points")
    raw = {
        "opp": store.read_table("nfl_ff_opportunity", "raw"),
        "snaps": store.read_table("nfl_snaps", "raw"),
        "stats": store.read_table("nfl_player_stats", "raw"),
        "depth": store.read_table("nfl_depth", "raw"),
    }
    exp = expected_frame(raw["opp"], points, leagues)
    active = stat_line.played_rows(points, exp, raw["snaps"], raw["opp"])
    history = stat_line.history_table(active, stat_line.usage_frame(raw["opp"], raw["snaps"], raw["stats"]))
    feats = stat_line.features(active, history, raw["depth"]).filter(pl.col("season") >= 2019)
    protocol = bias_check.protocol_rows().filter(pl.col("protocol")).select(KEYS)
    rows = (
        protocol.join(reg_keys(), on=KEYS, how="semi")
        .join(off.filter(~pl.col("is_future")).select(*KEYS, pl.col("projection").alias("cur")), on=KEYS)
        .join(points.select(*KEYS, "points"), on=KEYS)
        .filter(pl.col("season").is_in(SCORED) & scored_weeks())
    )
    print("\n== seeds: protocol-row RMSE gain (%) of q * E against E ==")
    draws = [(s,) for s in range(6)] + [tuple(range(3 * b, 3 * b + 3)) for b in range(6)]
    for seeds in draws:
        q = stat_line.history_chance(feats, seeds).filter(pl.col("season").is_in(SCORED))
        d = rows.join(q, on=["gsis_id", "season", "week"]).with_columns(
            (pl.col("q") * pl.col("cur")).alias("cand")
        )
        out = []
        for lid in sorted(names):
            g = d.filter(pl.col("league_id") == lid)
            a = float(((g["cur"] - g["points"]) ** 2).mean() ** 0.5)
            b = float(((g["cand"] - g["points"]) ** 2).mean() ** 0.5)
            out.append(f"{names[lid]} {100 * (a - b) / a:+.3f}")
        print(f"   seeds {seeds}: " + ", ".join(out))


def fit_rows(proj: pl.DataFrame, statline_tiers: bool) -> pl.DataFrame:
    """2021-2023 residuals; with `statline_tiers`, flagged so tiers are cut on stat-line games (as
    distributions.run does with the stat-line model on)."""
    fit = residual_frame(proj.filter(pl.col("season").is_between(*FIT)), store.read_table("player_points"))
    return with_stat_line_flag(fit, store.read_table("proj_baseline")) if statline_tiers else fit


def shapes(proj: pl.DataFrame, statline_tiers: bool = False) -> pl.DataFrame:
    fit = fit_rows(proj, statline_tiers)
    return estimate_marginals(fit)


def score_shapes(rows: pl.DataFrame, marg: pl.DataFrame) -> pl.DataFrame:
    """rows: KEYS, position, projection, points. Adds tier, pinball, covered."""
    parts = []
    for (lid, pos), g in rows.filter(pl.col("projection") > MIN_PROJECTION).group_by("league_id", "position"):
        m = marg.filter((pl.col("league_id") == lid) & (pl.col("position") == pos))
        edges = m.filter(pl.col("tier") >= 0).group_by("tier").agg(pl.col("proj_max").first()).sort("tier")
        cut = edges["proj_max"].to_numpy()[:2]
        tier = np.digitize(g["projection"].to_numpy(), cut)
        ratio = {
            t: m.filter(pl.col("tier") == t).sort("tau")["ratio"].to_numpy() for t in range(3)
        }
        q = np.stack([ratio[t] for t in tier]) * g["projection"].to_numpy()[:, None]
        y = g["points"].to_numpy()[:, None]
        err = y - q
        pin = np.maximum(LEVELS * err, (LEVELS - 1) * err).mean(axis=1)
        lo, hi = q[:, 9], q[:, 89]  # 10% and 90%
        covered = (y[:, 0] >= lo) & (y[:, 0] <= hi)
        parts.append(g.with_columns(pl.Series("tier", tier), pl.Series("pinball", pin), pl.Series("covered", covered)))
    return pl.concat(parts)


def mean_ratio(proj: pl.DataFrame, marg: pl.DataFrame, statline_tiers: bool = False) -> pl.DataFrame:
    fit = fit_rows(proj, statline_tiers)
    fit = fit.filter(pl.col("projection") > MIN_PROJECTION).select(*KEYS, "position", "projection", "points")
    tiered = score_shapes(fit, marg)
    return tiered.group_by("league_id", "tier").agg(
        (pl.col("points") / pl.col("projection")).mean().alias("mean_ratio"),
        (pl.col("points").sum() / pl.col("projection").sum()).alias("sum_ratio"),
        pl.len().alias("n"),
    )


def shapes_part(off: pl.DataFrame, on: pl.DataFrame, names: dict[str, str]) -> None:
    points = store.read_table("player_points").select(*KEYS, "points")
    q = store.read_table("stat_line")
    keep = lambda f: f.filter(~pl.col("is_future") & (pl.col("week") <= REG_LAST_WEEK))  # noqa: E731
    off, on = keep(off), keep(on)
    m_off, m_on = shapes(off), shapes(on, statline_tiers=True)
    statless = on.join(off.select(KEYS), on=KEYS, how="anti")
    e_statless = statless.join(q, on=["gsis_id", "season", "week"]).with_columns(
        pl.col("projection") / pl.col("q")
    )
    test = lambda f: f.filter(pl.col("season").is_in(SCORED) & scored_weeks() & pl.col("has_history")).select(  # noqa: E731
        *KEYS, "position", "projection"
    ).join(points, on=KEYS)
    arms = {
        "off": score_shapes(test(off), m_off),
        "on": score_shapes(test(on), m_on),
        "off_all": score_shapes(test(pl.concat([off, e_statless.select(off.columns)])), m_off),
        "on_stat": score_shapes(test(on).join(off.select(KEYS), on=KEYS, how="semi"), m_on),
    }
    print("\n== shapes: held-out pinball and 80% coverage by league and tier ==")
    table = []
    for arm, d in arms.items():
        for (lid, tier), g in d.group_by("league_id", "tier"):
            table.append({"league": names[lid], "tier": tier, "arm": arm, "n": g.height,
                          "pinball": float(g["pinball"].mean()), "cover80": float(g["covered"].mean())})
        for (lid,), g in d.group_by("league_id"):
            table.append({"league": names[lid], "tier": -1, "arm": arm, "n": g.height,
                          "pinball": float(g["pinball"].mean()), "cover80": float(g["covered"].mean())})
    print(pl.DataFrame(table).pivot(on="arm", index=["league", "tier"], values=["pinball", "cover80", "n"]).sort("league", "tier"))
    print("paired weekly t, pinball of on against off_all (positive: on better):")
    for lid in sorted(names):
        a = arms["off_all"].filter(pl.col("league_id") == lid).select(*KEYS, pl.col("pinball").alias("a"))
        b = arms["on"].filter(pl.col("league_id") == lid).select(*KEYS, pl.col("pinball").alias("b"))
        w = a.join(b, on=KEYS).group_by("season", "week").agg((pl.col("a") - pl.col("b")).mean().alias("d"))
        d = w["d"].to_numpy()
        print(f"   {names[lid]}: mean diff {d.mean():+.4f}, t {d.mean() / (d.std(ddof=1) / np.sqrt(len(d))):+.2f}, weeks {len(d)}")
    print("\n== mean ratio points / projection on the 2021-2023 fit rows, by tier ==")
    r = pl.concat([
        mean_ratio(off, m_off).with_columns(pl.lit("off").alias("arm")),
        mean_ratio(on, m_on, statline_tiers=True).with_columns(pl.lit("on").alias("arm")),
    ]).with_columns(pl.col("league_id").replace_strict(names).alias("league"))
    print(r.pivot(on="arm", index=["league", "tier"], values=["mean_ratio", "sum_ratio", "n"]).sort("league", "tier"))


def main() -> None:
    off = pl.read_parquet(sys.argv[1])
    on = store.read_table("proj_learned")
    leagues = store.read_table("leagues", "raw")
    names = {r["league_id"]: r["name"].split()[0] for r in leagues.iter_rows(named=True)}
    shapes_part(off, on, names)
    seeds_part(off, names)


if __name__ == "__main__":
    main()
