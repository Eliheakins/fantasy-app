"""Two-part (hurdle) projection: q = P(stat line | active) times E[points | stat line].

About 6% of skill player_points rows are stat-less appearances (every stat 0, no
nfl_ff_opportunity row). Training drops them, the scorecard scores them, and the learned model is
about 4 points too high on them (bias_check.py part 6). Union training (union_check.py) fixed the
scorecard rows but cost 0.17% on protocol rows in Colgate.

Candidate: projection = q * E, where E is the current learned model unchanged and q is the
chance that an active player-game (one with a player_points row) has a stat line (an
nfl_ff_opportunity row; the stat-less rows score 0 or near it). Two versions of q, each fit on
earlier seasons only (2019 to s-1) and league independent (both leagues have the same rows):
  hgb     HistGradientBoostingClassifier on pre-game features: EWMAs (half-life 4 games, strictly
          before the game, `learn.lag_asof`) of offensive and special-teams snap share, target
          share, targets, carries and the stat-line rate over earlier active games; the last
          snap share, games played and weeks since the last active game (`learn.latest_asof`
          one week back); the game's depth rank (as `learn` uses it); position.
  cell    the stat-line rate by position x depth rank (1, 2, 3, 4+ or none) x snap-share EWMA
          bucket, falling back to position.
E for rows the current model never projected (the stat-less ones) comes from the current model
on its own state (built from stat-line games only), as union_check.py does and as the live path
projects any rostered player.

Scored on 2024, 2025 and 2026 weeks 1 to 6 (regular season), both leagues:
  scorecard  every skill player_points row
  protocol   compare_to_baseline's rows (has_history, size-calibrated baseline above 3)
Ship rule (fixed before running): on scorecard rows the hurdle lowers RMSE in both leagues with
pooled paired per-week |t| >= 2 in each, no season with t <= -1, a gain above twice refit noise
(0.08% Colgate, 0.20% YinzBurgh), and protocol rows no worse than 0.05%.

Writes the hgb hurdle's walk-forward projections (2021 on, past games) to PREDS for a lineup
regret check.

Run from the repo root: OMP_NUM_THREADS=3 uv run python research/hurdle_check.py
"""

import numpy as np
import polars as pl
from sklearn.ensemble import HistGradientBoostingClassifier

import bias_check
import union_check
from fantasy import store
from fantasy.stages import learn
from fantasy.stages.backtest import size_tiers
from fantasy.stages.learn import KEY, lag_asof, latest_asof
from fantasy.stages.project import POSITIONS, expected_frame

PRED_SEASONS = (2021, 2022, 2023, 2024, 2025, 2026)
SCORED = (2024, 2025, 2026)
LAST_SCORED_WEEK_2026 = 6
FIRST_FIT_SEASON = 2019  # lags need a prior season
KEYS = union_check.KEYS
NOISE = {"Colgate": 0.04, "YinzBurgh": 0.10}  # refit sd of the current model's RMSE, percent
MAX_PROTOCOL_LOSS = 0.05  # percent
MIN_T = 2.0
WEEKS_PER_SEASON = 18
PREDS = (
    "/private/tmp/claude-501/-Users-eliheakins-personal-fantasy-app/"
    "230639a7-242c-4003-bae2-a92998c4f96c/scratchpad/preds/hurdle.parquet"
)
LAGGED = ["snap", "st", "tshare", "tgt", "car", "statline"]
FEATURES = [f"h_{c}" for c in LAGGED] + ["snap_last", "n_prior", "weeks_since", "depth_rank"]
pl.Config(tbl_rows=80, tbl_cols=16, tbl_width_chars=200, float_precision=4)


def active_rows(points: pl.DataFrame, exp: pl.DataFrame) -> pl.DataFrame:
    """One row per skill player-game with a player_points row (one league: the row sets match),
    with `statline` 1 when an expected-points (opportunity) row exists."""
    lid = sorted(points["league_id"].unique().to_list())[0]
    rows = points.filter((pl.col("league_id") == lid) & pl.col("position").is_in(POSITIONS))
    have = exp.filter(pl.col("league_id") == lid).select(KEY).with_columns(statline=pl.lit(1.0))
    return (
        rows.select(*KEY, "position", "season_type")
        .unique(KEY, keep="first", maintain_order=True)
        .join(have, on=KEY, how="left")
        .with_columns(pl.col("statline").fill_null(0.0))
    )


def q_features(rows: pl.DataFrame, raw: dict) -> pl.DataFrame:
    """Pre-game features for each active row, from earlier active games only."""
    opp = raw["opp"].select(
        pl.col("player_id").alias("gsis_id"),
        "season",
        "week",
        pl.col("rec_attempt").cast(pl.Float64).alias("tgt"),
        pl.col("rush_attempt").cast(pl.Float64).alias("car"),
    ).unique(KEY, keep="first", maintain_order=True)
    snaps = (
        raw["snaps"]
        .filter(pl.col("gsis_id").is_not_null())
        .select(*KEY, pl.col("offense_pct").cast(pl.Float64).alias("snap"),
                pl.col("st_pct").cast(pl.Float64).alias("st"))
        .unique(KEY, keep="first", maintain_order=True)
    )
    share = (
        raw["stats"].filter(pl.col("season_type") == "REG")
        .select(pl.col("player_id").alias("gsis_id"), "season", "week",
                pl.col("target_share").cast(pl.Float64).alias("tshare"))
        .unique(KEY, keep="first", maintain_order=True)
    )
    hist = (
        rows.select(*KEY, "statline")
        .join(opp, on=KEY, how="left")
        .join(snaps, on=KEY, how="left")
        .join(share, on=KEY, how="left")
        .with_columns(pl.col("tgt", "car").fill_null(0.0))
        .sort("gsis_id", "season", "week")
        .with_columns(
            pl.int_range(1, pl.len() + 1).over("gsis_id").cast(pl.Float64).alias("n_prior"),
            (pl.col("season") * WEEKS_PER_SEASON + pl.col("week")).cast(pl.Float64).alias("when"),
            pl.col("snap").alias("snap_last"),
        )
    )
    depth = raw["depth"].unique(KEY, keep="first", maintain_order=True)
    out = lag_asof(rows, hist, "gsis_id", LAGGED, "h")  # strictly before the game
    out = latest_asof(out, hist, "gsis_id", ["snap_last", "n_prior", "when"], shift=1)
    return out.join(depth, on=KEY, how="left").with_columns(
        (pl.col("season") * WEEKS_PER_SEASON + pl.col("week") - pl.col("when") - 1)
        .alias("weeks_since"),
        pl.col("n_prior").fill_null(0.0),
    )


def q_design(frame: pl.DataFrame) -> np.ndarray:
    onehot = [(frame["position"] == p).cast(pl.Float64).to_numpy() for p in POSITIONS]
    numeric = [frame[c].cast(pl.Float64).to_numpy() for c in FEATURES]
    return np.column_stack(numeric + onehot)


def cell_key(frame: pl.DataFrame) -> pl.DataFrame:
    depth = (
        pl.when(pl.col("depth_rank").is_null()).then(pl.lit("none"))
        .when(pl.col("depth_rank") >= 4).then(pl.lit("4+"))
        .otherwise(pl.col("depth_rank").cast(pl.Int64).cast(pl.String))
    )
    snap = pl.col("h_snap").cut([0.1, 0.3, 0.6]).cast(pl.String).fill_null("none")
    return frame.with_columns(depth.alias("d_cell"), snap.alias("s_cell"))


def fit_q(feats: pl.DataFrame, seed: int = 0) -> pl.DataFrame:
    """KEY, statline, q_hgb, q_cell for PRED_SEASONS, each season from a fit on 2019..s-1."""
    feats = cell_key(feats)
    parts = []
    for season in PRED_SEASONS:
        train = feats.filter(pl.col("season").is_between(FIRST_FIT_SEASON, season - 1))
        test = feats.filter(pl.col("season") == season)
        model = HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=80,
            l2_regularization=5.0, random_state=seed,
        ).fit(q_design(train), train["statline"].to_numpy())
        cells = train.group_by("position", "d_cell", "s_cell").agg(
            pl.col("statline").mean().alias("q_c"), pl.len().alias("n_c")
        ).filter(pl.col("n_c") >= 30)
        pos = train.group_by("position").agg(pl.col("statline").mean().alias("q_p"))
        parts.append(
            test.with_columns(pl.Series("q_hgb", model.predict_proba(q_design(test))[:, 1]))
            .join(cells, on=["position", "d_cell", "s_cell"], how="left")
            .join(pos, on="position", how="left")
            .with_columns(pl.coalesce("q_c", "q_p").alias("q_cell"),
                          pl.lit(float(train["statline"].mean())).alias("q_const"))
            .select(*KEY, "season_type", "statline", "q_hgb", "q_cell", "q_const")
        )
    return pl.concat(parts)


def calibration(q: pl.DataFrame) -> None:
    scored = q.filter(pl.col("season").is_in(SCORED) & (pl.col("season_type") == "REG"))
    y = scored["statline"].to_numpy()
    print(f"\n-- q on scored seasons ({scored.height} rows, stat-line rate {y.mean():.4f})")
    for col in ("q_hgb", "q_cell", "q_const"):
        p = scored[col].to_numpy()
        print(f"   {col}: Brier {np.mean((p - y) ** 2):.5f}, mean q {p.mean():.4f}")
    print("   q_hgb calibration by decile of q:")
    print(
        scored.with_columns(pl.col("q_hgb").qcut(10, allow_duplicates=True).alias("bin"))
        .group_by("bin").agg(pl.len().alias("n"), pl.col("q_hgb").mean().alias("mean_q"),
                             pl.col("statline").mean().alias("observed"))
        .sort("mean_q")
    )


def score(d: pl.DataFrame, cand: str) -> dict[str, float | int | str]:
    by_week = d.group_by("season", "week").agg(
        ((pl.col("cur") - pl.col("points")) ** 2).mean().alias("a"),
        ((pl.col(cand) - pl.col("points")) ** 2).mean().alias("b"),
    )
    diff = (by_week["a"] - by_week["b"]).to_numpy()
    t = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))) if len(diff) > 2 else np.nan
    a = float(((d["cur"] - d["points"]) ** 2).mean() ** 0.5)
    b = float(((d[cand] - d["points"]) ** 2).mean() ** 0.5)
    return {
        "n": d.height,
        "rmse_cur": round(a, 4),
        "rmse": round(b, 4),
        "gain_pct": round(100 * (a - b) / a, 3),
        "mae_cur": round(float((d["cur"] - d["points"]).abs().mean()), 4),
        "mae": round(float((d[cand] - d["points"]).abs().mean()), 4),
        "me_cur": round(float((d["cur"] - d["points"]).mean()), 3),
        "me": round(float((d[cand] - d["points"]).mean()), 3),
        "t": round(t, 2),
        "weeks_better": f"{int((diff > 0).sum())}/{len(diff)}",
    }


def with_tiers(d: pl.DataFrame) -> pl.DataFrame:
    """Thirds of the current projection per league and position, edges from 2021 to 2023."""
    parts = []
    for _, g in d.group_by("league_id", "position"):
        train = g.filter(pl.col("season") < SCORED[0])["cur"].to_numpy()
        parts.append(g.with_columns(pl.Series("tier", size_tiers(train, g["cur"].to_numpy()))))
    return pl.concat(parts)


def report(preds: pl.DataFrame, protocol: pl.DataFrame) -> None:
    scored = with_tiers(preds).filter(
        pl.col("season").is_in(SCORED)
        & (pl.col("season_type") == "REG")
        & ((pl.col("season") < 2026) | (pl.col("week") <= LAST_SCORED_WEEK_2026))
    )
    verdict: dict[tuple[str, str, str], dict] = {}
    for label, rows in (("scorecard", scored), ("protocol", scored.join(protocol, on=KEYS, how="semi"))):
        for cand in ("hurdle", "hurdle_cell", "cand"):
            out = []
            for (league,), g in rows.group_by("league"):
                pooled = score(g, cand)
                verdict[(label, cand, league)] = pooled
                out.append({"league": league, "cut": "all", **pooled})
                for (s,), gs in g.group_by("season"):
                    verdict[(label, cand, f"{league}-{s}")] = score(gs, cand)
                    out.append({"league": league, "cut": str(s), **verdict[(label, cand, f"{league}-{s}")]})
                if label == "scorecard":
                    for (p,), gp in g.group_by("position"):
                        out.append({"league": league, "cut": p, **score(gp, cand)})
                    for (tier,), gt in g.group_by("tier"):
                        out.append({"league": league, "cut": f"tier{tier}", **score(gt, cand)})
                    for (no,), gn in g.group_by("no_opp"):
                        out.append({"league": league, "cut": f"stat-less={no}", **score(gn, cand)})
            name = {"hurdle": "hurdle (hgb q)", "hurdle_cell": "hurdle (cell q)", "cand": "union"}[cand]
            print(f"\n-- {label} rows: {name} against current")
            print(pl.DataFrame(out).sort("league", "cut"))
    for cand in ("hurdle", "hurdle_cell", "cand"):
        checks = []
        for league, noise in NOISE.items():
            sc = verdict[("scorecard", cand, league)]
            seasons = [verdict[("scorecard", cand, f"{league}-{s}")]["t"] for s in SCORED]
            pr = verdict[("protocol", cand, league)]
            checks += [
                sc["gain_pct"] > 2 * noise,
                abs(sc["t"]) >= MIN_T,
                all(t > -1 for t in seasons),
                pr["gain_pct"] >= -MAX_PROTOCOL_LOSS,
            ]
        print(f"ship rule, {cand}: {'CLEARS' if all(checks) else 'does not clear'} {checks}")


def q_seed_noise(feats: pl.DataFrame, protocol: pl.DataFrame, names: dict[str, str]) -> None:
    """Protocol-row gain of the hgb hurdle over q refits with other seeds (the classifier
    early-stops on a seeded validation split). On these rows the current model is proj_learned."""
    learned = store.read_table("proj_learned").filter(~pl.col("is_future"))
    rows = (
        protocol.join(learned.select(*KEYS, pl.col("projection").alias("cur")), on=KEYS)
        .join(store.read_table("player_points").select(*KEYS, "points"), on=KEYS)
        .filter(pl.col("season").is_in(SCORED) & ((pl.col("season") < 2026) | (pl.col("week") <= LAST_SCORED_WEEK_2026)))
    )
    print("\n-- protocol-row gain (%) over q seeds")
    for seed in range(6):
        q = fit_q(feats, seed).filter(pl.col("season_type") == "REG").select("gsis_id", "season", "week", "q_hgb")
        d = rows.join(q, on=["gsis_id", "season", "week"]).with_columns(
            (pl.col("q_hgb") * pl.col("cur")).alias("hurdle")
        )
        print(f"   seed {seed}: " + ", ".join(
            f"{names[lid]} {score(g, 'hurdle')['gain_pct']:+.3f}"
            for (lid,), g in d.sort("league_id").group_by("league_id", maintain_order=True)
        ))


def main() -> None:
    leagues = store.read_table("leagues", "raw")
    names = {r["league_id"]: r["name"].split()[0] for r in leagues.iter_rows(named=True)}
    points = store.read_table("player_points")
    raw = {
        "opp": store.read_table("nfl_ff_opportunity", "raw"),
        "snaps": store.read_table("nfl_snaps", "raw"),
        "stats": store.read_table("nfl_player_stats", "raw"),
        "depth": store.read_table("nfl_depth", "raw"),
        "lines": store.read_table("team_games"),
        "extras": learn.load_extras(),
    }
    exp = expected_frame(raw["opp"], points, leagues)
    q = fit_q(q_features(active_rows(points, exp), raw))
    calibration(q)

    extra = union_check.union_rows(exp, points)
    union_check.SCORED = PRED_SEASONS  # current and union model for every season written out
    preds = pl.concat([union_check.league_preds(lid, exp, extra, raw) for lid in names])
    learned = store.read_table("proj_learned").filter(~pl.col("is_future"))
    check = preds.filter(~pl.col("no_opp")).join(learned.select(*KEYS, "projection"), on=KEYS)
    print(f"\ncurrent model against proj_learned: {check.height} rows, max abs diff "
          f"{float((check['cur'] - check['projection']).abs().max()):.4f}")
    preds = preds.join(q.drop("statline"), on=["gsis_id", "season", "week"], how="left")
    missing = int(preds["q_hgb"].is_null().sum())
    if missing:
        raise ValueError(f"{missing} prediction rows have no q")
    preds = preds.with_columns(
        (pl.col("q_hgb") * pl.col("cur")).alias("hurdle"),
        (pl.col("q_cell") * pl.col("cur")).alias("hurdle_cell"),
        pl.col("league_id").replace_strict(names).alias("league"),
    )
    reg = preds.filter(pl.col("season_type") == "REG")
    reg.select(*KEYS, pl.col("hurdle").alias("projection")).write_parquet(PREDS)
    print(f"wrote {reg.height} rows to {PREDS}")
    protocol = bias_check.protocol_rows().filter(pl.col("protocol")).select(KEYS)
    report(preds, protocol)


if __name__ == "__main__":
    main()
