"""Should the learned model also train on player_points rows that have no opportunity row?

Training rows need an `nfl_ff_opportunity` row and a `player_points` row
(`project.expected_frame`), but the scorecard scores any `player_points` row. About 6% of skill
rows are nflverse weekly rows with every stat 0 (special teams, a few offensive snaps); the model
never sees them, so it over-projects them (bias_check.py part 6).

Candidate: train on the union. A row with no opportunity row gets zero expected points, targets,
carries, attempts and expected touchdowns for that game (snap share and target share as nflverse
has them), target = its points; it enters the player's lagged state like any other game.

Both models use `learn`'s features and settings, walk-forward by season (trained on earlier
seasons), scored on 2024, 2025 and 2026 on two row sets:
  scorecard  every skill player_points row (the current model projects the union-only rows from
             its own state, as the live path does for any rostered player)
  protocol   compare_to_baseline's rows (has_history, size-calibrated baseline above 3)
Ship rule (fixed before running): lower RMSE on the scorecard set in both leagues with pooled
paired per-week |t| >= 2, and protocol RMSE no more than 0.1% worse.

Run from the repo root: OMP_NUM_THREADS=3 uv run python research/union_check.py
"""

import numpy as np
import polars as pl

import bias_check
from fantasy import store
from fantasy.stages import learn
from fantasy.stages.project import GROUP, POSITIONS, expected_frame, history_targets

SCORED = (2024, 2025, 2026)
KEYS = [*GROUP, "season", "week"]
ZEROED = ["tgt", "car", "att", "rec_td_exp", "rush_td_exp"]
MAX_PROTOCOL_LOSS = 0.1  # percent
MIN_T = 2.0
pl.Config(tbl_rows=40, tbl_cols=14, tbl_width_chars=180, float_precision=3)


def union_rows(exp: pl.DataFrame, points: pl.DataFrame) -> pl.DataFrame:
    """player_points skill rows with no expected-points row, shaped like `exp` (exp_pts 0)."""
    extra = (
        points.filter(pl.col("position").is_in(POSITIONS))
        .join(exp.select(KEYS), on=KEYS, how="anti")
        .select(*KEYS, "position", "team", "points", pl.lit(0.0).alias("exp_pts"))
    )
    return extra.select(exp.columns)


def season_preds(history: pl.DataFrame, test: pl.DataFrame, season: int) -> np.ndarray:
    seasons = sorted(history["season"].unique().to_list())
    train = history.filter(pl.col("season").is_in(learn.train_seasons(season, seasons)))
    return learn.fit_predict(
        learn.design(train, True), train["points"].to_numpy(), learn.design(test, True)
    )


def league_preds(lid: str, exp: pl.DataFrame, extra: pl.DataFrame, raw: dict) -> pl.DataFrame:
    """KEYS, points, cur (current model), cand (union model), no_opp, for seasons SCORED."""
    exp_l, extra_l = exp.filter(pl.col("league_id") == lid), extra.filter(pl.col("league_id") == lid)
    union = pl.concat([exp_l, extra_l])
    games_cur = learn.games_frame(exp_l, raw["opp"], raw["snaps"], raw["stats"])
    games_union = learn.games_frame(union, raw["opp"], raw["snaps"], raw["stats"]).join(
        extra_l.select(KEYS).with_columns(pl.lit(True).alias("no_opp")), on=KEYS, how="left"
    ).with_columns([pl.when(pl.col("no_opp")).then(0.0).otherwise(pl.col(c)).alias(c) for c in ZEROED])
    state_cur, state_union = learn.state_frame(games_cur), learn.state_frame(games_union)

    def features(targets: pl.DataFrame, state: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
        return learn.build_features(history_targets(targets), state, raw["lines"], raw["extras"]).join(
            games.select(*KEYS, "points"), on=KEYS
        )

    hist_cur = features(exp_l, state_cur, games_cur)
    extra_cur = features(extra_l, state_cur, games_union)  # the current model's view of them
    hist_union = features(union, state_union, games_union)
    parts = []
    for season in SCORED:
        test_cur = pl.concat([hist_cur, extra_cur], how="diagonal_relaxed").filter(pl.col("season") == season)
        cur = test_cur.select(*KEYS, "position", "points").with_columns(
            pl.Series("cur", season_preds(hist_cur, test_cur, season))
        )
        test_union = hist_union.filter(pl.col("season") == season)
        cand = test_union.select(KEYS).with_columns(
            pl.Series("cand", season_preds(hist_union, test_union, season))
        )
        parts.append(cur.join(cand, on=KEYS))
    return pl.concat(parts).join(
        extra_l.select(KEYS).with_columns(pl.lit(True).alias("no_opp")), on=KEYS, how="left"
    ).with_columns(pl.col("no_opp").fill_null(False))


def score(d: pl.DataFrame) -> dict[str, float | int | str]:
    by_week = d.group_by("season", "week").agg(
        ((pl.col("cur") - pl.col("points")) ** 2).mean().alias("a"),
        ((pl.col("cand") - pl.col("points")) ** 2).mean().alias("b"),
    )
    diff = (by_week["a"] - by_week["b"]).to_numpy()
    t = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))) if len(diff) > 2 else np.nan
    a = float(((d["cur"] - d["points"]) ** 2).mean() ** 0.5)
    b = float(((d["cand"] - d["points"]) ** 2).mean() ** 0.5)
    return {
        "n": d.height,
        "rmse_cur": round(a, 4),
        "rmse_cand": round(b, 4),
        "gain_pct": round(100 * (a - b) / a, 3),
        "me_cur": round(float((d["cur"] - d["points"]).mean()), 3),
        "me_cand": round(float((d["cand"] - d["points"]).mean()), 3),
        "t": round(t, 2),
        "weeks_better": f"{int((diff > 0).sum())}/{len(diff)}",
    }


def main() -> None:
    leagues = store.read_table("leagues", "raw")
    names = {r["league_id"]: r["name"].split()[0] for r in leagues.iter_rows(named=True)}
    points = store.read_table("player_points")
    raw = {
        "opp": store.read_table("nfl_ff_opportunity", "raw"),
        "snaps": store.read_table("nfl_snaps", "raw"),
        "stats": store.read_table("nfl_player_stats", "raw"),
        "lines": store.read_table("team_games"),
        "extras": learn.load_extras(),
    }
    exp = expected_frame(raw["opp"], points, leagues)
    extra = union_rows(exp, points)
    print(f"union-only rows (all seasons, both leagues): {extra.height}, mean points {extra['points'].mean():.3f}")
    preds = pl.concat([league_preds(lid, exp, extra, raw) for lid in names])
    learned = store.read_table("proj_learned").filter(~pl.col("is_future"))
    check = preds.filter(~pl.col("no_opp")).join(learned.select(*KEYS, "projection"), on=KEYS)
    print(f"current model check against proj_learned: {check.height} rows, max abs diff "
          f"{float((check['cur'] - check['projection']).abs().max()):.4f}")
    protocol = bias_check.protocol_rows().filter(pl.col("protocol")).select(KEYS)
    preds = preds.with_columns(pl.col("league_id").replace_strict(names).alias("league"))
    verdict = []
    for label, rows in (("scorecard", preds), ("protocol", preds.join(protocol, on=KEYS, how="semi"))):
        out = []
        for (league,), g in rows.group_by("league"):
            pooled = score(g)
            out.append({"league": league, "season": "all", "pos": "ALL", **pooled})
            verdict.append((label, league, pooled))
            for (s,), gs in g.group_by("season"):
                out.append({"league": league, "season": str(s), "pos": "ALL", **score(gs)})
            for (p,), gp in g.group_by("position"):
                out.append({"league": league, "season": "all", "pos": p, **score(gp)})
        print(f"\n-- {label} rows")
        print(pl.DataFrame(out).sort("league", "pos", "season"))
    sc = [v for lab, _, v in verdict if lab == "scorecard"]
    pr = [v for lab, _, v in verdict if lab == "protocol"]
    clears = all(v["gain_pct"] > 0 and abs(v["t"]) >= MIN_T for v in sc) and all(
        v["gain_pct"] >= -MAX_PROTOCOL_LOSS for v in pr
    )
    print(f"\nship rule: {'CLEARS' if clears else 'does not clear'}")


if __name__ == "__main__":
    main()
