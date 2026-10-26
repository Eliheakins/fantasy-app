"""Rerun of the two-part projection on played games (review fix: the universe no longer depends on
the outcome).

Played = offensive snaps (nfl_snaps) or a player_points row; a played game with no player_points
row scores 0. Reads the production outputs of a switch-on `learn` run: `proj_learned` (q * E on
every played game, walk-forward), the `stat_line` table (q), and E = q * E / q. Scored on 2024,
2025 and 2026 weeks 1 to 6 (weeks 1 to 18), both leagues:
  played    every played skill game with a learned projection
  protocol  compare_to_baseline's rows (has_history, size-calibrated baseline above 3)
by season, position, tier (thirds of E per league and position, edges from 2021-2023), with paired
weekly t; Brier and calibration of q against the stat-line label (a baseline row exists).
Ship rule (fixed before the rerun): played RMSE lower in both leagues with pooled |t| >= 2 each,
no season t <= -1; protocol rows no worse than 0.05%.
Then the held-out shapes of hurdle_followup_check.py (tiers cut on stat-line games when on).

Run after a switch-on learn and distributions, from the repo root:
  OMP_NUM_THREADS=3 uv run python research/hurdle_played_check.py <switch-off proj_learned parquet>
"""

import sys

import bias_check
import hurdle_followup_check as followup
import numpy as np
import polars as pl

from fantasy import stat_line_table, store
from fantasy.stages.backtest import size_tiers

KEYS = ["league_id", "gsis_id", "season", "week"]
SCORED = (2024, 2025, 2026)
MIN_T = 2.0
MAX_PROTOCOL_LOSS = 0.05
pl.Config(tbl_rows=80, tbl_cols=14, tbl_width_chars=200, float_precision=4)


def played_frame() -> pl.DataFrame:
    on = store.read_table("proj_learned").filter(~pl.col("is_future") & (pl.col("week") <= 18))
    q = stat_line_table.stored()
    if q is None:
        raise SystemExit("run learn with stat_line_model = true first")
    e = stat_line_table.divide(on, q, ["gsis_id", "season", "week"])
    base_keys = store.read_table("proj_baseline").filter(~pl.col("is_future")).select(KEYS).unique()
    points = store.read_table("player_points").select(*KEYS, "points")
    return (
        on.select(*KEYS, "position", pl.col("projection").alias("hurdle"))
        .join(e.select(*KEYS, pl.col("projection").alias("cur")), on=KEYS)
        .join(q, on=["gsis_id", "season", "week"])
        .join(points, on=KEYS, how="left")
        .join(base_keys.with_columns(pl.lit(1.0).alias("statline")), on=KEYS, how="left")
        .with_columns(pl.col("points").fill_null(0.0), pl.col("statline").fill_null(0.0))
    )


def with_tiers(d: pl.DataFrame) -> pl.DataFrame:
    parts = []
    for _, g in d.group_by("league_id", "position"):
        train = g.filter(pl.col("season").is_between(2021, 2023))["cur"].to_numpy()
        parts.append(g.with_columns(pl.Series("tier", size_tiers(train, g["cur"].to_numpy()))))
    return pl.concat(parts)


def score(d: pl.DataFrame) -> dict[str, float | int | str]:
    by_week = d.group_by("season", "week").agg(
        ((pl.col("cur") - pl.col("points")) ** 2).mean().alias("a"),
        ((pl.col("hurdle") - pl.col("points")) ** 2).mean().alias("b"),
    )
    diff = (by_week["a"] - by_week["b"]).to_numpy()
    t = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))) if len(diff) > 2 else np.nan
    a = float(np.sqrt(((d["cur"] - d["points"]) ** 2).to_numpy().mean()))
    b = float(np.sqrt(((d["hurdle"] - d["points"]) ** 2).to_numpy().mean()))
    return {
        "n": d.height,
        "rmse_E": round(a, 4),
        "rmse_qE": round(b, 4),
        "gain_pct": round(100 * (a - b) / a, 3),
        "me_E": round(float((d["cur"] - d["points"]).mean()), 3),
        "me_qE": round(float((d["hurdle"] - d["points"]).mean()), 3),
        "t": round(t, 2),
        "weeks": f"{int((diff > 0).sum())}/{len(diff)}",
    }


def main() -> None:
    names = {r["league_id"]: r["name"].split()[0] for r in store.read_table("leagues", "raw").iter_rows(named=True)}
    rows = with_tiers(played_frame()).filter(
        pl.col("season").is_in(SCORED) & ((pl.col("season") < 2026) | (pl.col("week") <= 6))
    ).with_columns(pl.col("league_id").replace_strict(names).alias("league"))
    y, p = rows["statline"].to_numpy(), rows["q"].to_numpy()
    print(f"q on scored played games (both leagues): stat-line rate {y.mean():.4f}, mean q {p.mean():.4f}, "
          f"Brier {np.mean((p - y) ** 2):.5f} (constant {np.mean((y.mean() - y) ** 2):.5f}); "
          f"no player_points row: {int((rows['points'].is_null()).sum())} (filled 0 above)")
    print(rows.filter(pl.col("league") == "Colgate").with_columns(pl.col("q").qcut(5, allow_duplicates=True).alias("bin"))
          .group_by("bin").agg(pl.len().alias("n"), pl.col("q").mean().alias("mean_q"), pl.col("statline").mean().alias("observed")).sort("mean_q"))
    protocol = bias_check.protocol_rows().filter(pl.col("protocol")).select(KEYS)
    verdict = {}
    for label, d in (("played", rows), ("protocol", rows.join(protocol, on=KEYS, how="semi"))):
        out = []
        for (league,), g in d.group_by("league"):
            verdict[(label, league)] = score(g)
            out.append({"league": league, "cut": "all", **verdict[(label, league)]})
            for (s,), gs in g.group_by("season"):
                verdict[(label, league, s)] = score(gs)
                out.append({"league": league, "cut": str(s), **verdict[(label, league, s)]})
            for (pos,), gp in g.group_by("position"):
                out.append({"league": league, "cut": pos, **score(gp)})
            for (tier,), gt in g.group_by("tier"):
                out.append({"league": league, "cut": f"tier{tier}", **score(gt)})
            if label == "played":
                for (st,), gs in g.group_by("statline"):
                    out.append({"league": league, "cut": f"statline={int(st)}", **score(gs)})
        print(f"\n-- {label} rows: q * E against E")
        print(pl.DataFrame(out).sort("league", "cut"))
    checks = []
    for league in names.values():
        sc = verdict[("played", league)]
        checks += [sc["gain_pct"] > 0, abs(sc["t"]) >= MIN_T]
        checks += [verdict[("played", league, s)]["t"] > -1 for s in SCORED]
        checks.append(verdict[("protocol", league)]["gain_pct"] >= -MAX_PROTOCOL_LOSS)
    print(f"\nship rule: {'CLEARS' if all(checks) else 'does not clear'} {checks}")
    followup.shapes_part(pl.read_parquet(sys.argv[1]), store.read_table("proj_learned"), names)


if __name__ == "__main__":
    main()
