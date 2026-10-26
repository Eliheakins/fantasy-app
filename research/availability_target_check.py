"""Should the chance-of-playing classifier predict a stat line rather than any offensive snaps?

The projection is E[points | stat line] (training rows are player-games with a `player_points`
row), but `stages/availability.py` labels a game played when the player had any offensive snaps.
The simulation multiplies the two for a flagged player's next game, so a game with snaps and no
stat line counts as played at full projection.

Universe and features: `availability.build_rows` (depth-chart regulars). Train 2019-2023, score
2024-2025, as `research/availability_check.py`. Three chances of playing:
  snaps     the production classifier (label: any offensive snaps)
  statline  the same classifier and features, label: a `player_points` row
  snaps*q   snaps times P(stat line | snaps) by position and depth rank, fit on 2019-2023
Expected points = p * projection, against actual points (0 with no stat line). The projection is
the learned model's, made as `learn` makes it (same features and settings, trained on seasons
before the scored one) for every row, including games the player missed, which have no
`proj_learned` row. Checked against `proj_learned` where both exist.

Run from the repo root: OMP_NUM_THREADS=3 uv run python research/availability_target_check.py
"""

import numpy as np
import polars as pl
from sklearn.metrics import brier_score_loss

from fantasy import store
from fantasy.stages import availability as av
from fantasy.stages import learn
from fantasy.stages.project import GROUP, expected_frame, history_targets

TRAIN_END = 2023
SCORED = (2024, 2025)
MIN_GROUP = 50  # depth-rank cells smaller than this use the position's rate
pl.Config(tbl_rows=40, tbl_cols=14, tbl_width_chars=180, float_precision=3)


def projections(universe: pl.DataFrame) -> pl.DataFrame:
    """Learned projection for every universe row of SCORED seasons, per league (models trained on
    earlier seasons only, as `learn.walk_forward` does for those seasons)."""
    leagues = store.read_table("leagues", "raw")
    opp = store.read_table("nfl_ff_opportunity", "raw")
    exp = expected_frame(opp, store.read_table("player_points"), leagues)
    games_all = learn.games_frame(
        exp, opp, store.read_table("nfl_snaps", "raw"), store.read_table("nfl_player_stats", "raw")
    )
    lines = store.read_table("team_games")
    extras = learn.load_extras()
    snaps = store.read_table("nfl_snaps", "raw").filter(pl.col("gsis_id").is_not_null())
    team = snaps.select(*learn.KEY, "team").unique(learn.KEY, keep="first")
    targets = learn.latest_asof(
        universe.filter(pl.col("season").is_in(SCORED)).select(*learn.KEY, "position"),
        team,
        "gsis_id",
        ["team"],
    )
    parts = []
    for lid in leagues["league_id"].to_list():
        games = games_all.filter(pl.col("league_id") == lid)
        state = learn.state_frame(games)
        history = learn.build_features(
            history_targets(exp.filter(pl.col("league_id") == lid)), state, lines, extras
        ).join(games.select(*GROUP, "season", "week", "points"), on=[*GROUP, "season", "week"])
        seasons = sorted(history["season"].unique().to_list())
        rows = learn.build_features(
            targets.with_columns(pl.lit(lid).alias("league_id")), state, lines, extras
        )
        for season in SCORED:
            train = history.filter(pl.col("season").is_in(learn.train_seasons(season, seasons)))
            test = rows.filter(pl.col("season") == season)
            pred = learn.fit_predict(
                learn.design(train, True), train["points"].to_numpy(), learn.design(test, True)
            )
            parts.append(
                test.select("league_id", *learn.KEY, "has_history").with_columns(
                    pl.Series("proj", pred)
                )
            )
    return pl.concat(parts)


def statline_rates(train: pl.DataFrame) -> pl.DataFrame:
    """P(stat line | snaps) by position and depth rank, small cells falling back to position."""
    played = train.filter(pl.col("played") == 1)
    by_pos = played.group_by("position").agg(pl.col("statline").mean().alias("q_pos"))
    cells = played.group_by("position", "depth_rank").agg(
        pl.col("statline").mean().alias("q_cell"), pl.len().alias("n_cell")
    )
    return cells.join(by_pos, on="position").select(
        "position",
        "depth_rank",
        pl.when(pl.col("n_cell") >= MIN_GROUP).then("q_cell").otherwise("q_pos").alias("q"),
    ), by_pos


def score(d: pl.DataFrame, cand: str) -> dict[str, float | int | str]:
    """Expected-points error of `cand` against snaps, with a paired per-week t."""
    ev = {c: pl.col(f"p_{c}") * pl.col("proj") for c in ("snaps", cand)}
    by_week = d.group_by("season", "week").agg(
        ((ev["snaps"] - pl.col("actual")) ** 2).mean().alias("a"),
        ((ev[cand] - pl.col("actual")) ** 2).mean().alias("b"),
    )
    diff = (by_week["a"] - by_week["b"]).to_numpy()
    t = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))) if len(diff) > 2 else np.nan
    m = d.select(
        ((ev["snaps"] - pl.col("actual")) ** 2).mean().sqrt().alias("rmse_snaps"),
        ((ev[cand] - pl.col("actual")) ** 2).mean().sqrt().alias("rmse_cand"),
        (ev["snaps"] - pl.col("actual")).mean().alias("me_snaps"),
        (ev[cand] - pl.col("actual")).mean().alias("me_cand"),
    ).row(0, named=True)
    gain = 100 * (m["rmse_snaps"] - m["rmse_cand"]) / m["rmse_snaps"]
    return {
        "n": d.height,
        **{k: round(v, 4) for k, v in m.items()},
        "gain_pct": round(gain, 2),
        "t": round(t, 2),
        "weeks_better": f"{int((diff > 0).sum())}/{len(diff)}",
    }


def main() -> None:
    have = store.read_table("player_points").select(*learn.KEY).unique()
    rows = (
        av.build_rows()
        .filter(pl.col("season") <= max(SCORED))
        .join(have.with_columns(pl.lit(1).alias("statline")), on=learn.KEY, how="left")
        .with_columns(pl.col("statline").fill_null(0))
    )
    train, test = rows.filter(pl.col("season") <= TRAIN_END), rows.filter(pl.col("season").is_in(SCORED))
    print(f"universe: train {train.height}, test {test.height}; test snaps share "
          f"{test['played'].mean():.3f}, stat-line share {test['statline'].mean():.3f}, "
          f"stat line without snaps {int(((test['statline'] == 1) & (test['played'] == 0)).sum())}")
    x_train, x_test = av.design(train), av.design(test)
    q, by_pos = statline_rates(train)
    test = (
        test.with_columns(
            p_snaps=pl.Series(av.fit_predict(x_train, train["played"].to_numpy(), x_test)),
            p_statline=pl.Series(av.fit_predict(x_train, train["statline"].to_numpy(), x_test)),
        )
        .join(q, on=["position", "depth_rank"], how="left")
        .join(by_pos, on="position", how="left")
        .with_columns((pl.col("p_snaps") * pl.coalesce("q", "q_pos")).alias("p_snaps_q"))
    )
    print("P(stat line | snaps) by position, 2019-2023:", dict(by_pos.sort("position").iter_rows()))
    flagged = pl.col("status") != "none"
    brier = []
    for label, mask in (("report-listed", flagged), ("all", pl.lit(True))):
        g = test.filter(mask)
        for name, col, target in (
            ("snaps", "p_snaps", "played"),
            ("snaps", "p_snaps", "statline"),
            ("statline", "p_statline", "statline"),
            ("snaps*q", "p_snaps_q", "statline"),
        ):
            brier.append({"rows": label, "model": name, "target": target, "n": g.height,
                          "brier": round(float(brier_score_loss(g[target], g[col])), 5)})
    print(pl.DataFrame(brier))

    proj = projections(rows)
    learned = store.read_table("proj_learned").filter(~pl.col("is_future"))
    check = proj.join(learned.select("league_id", *learn.KEY, "projection"), on=["league_id", *learn.KEY])
    print(f"projection check against proj_learned: {check.height} rows, max abs diff "
          f"{float((check['proj'] - check['projection']).abs().max()):.4f}")
    points = store.read_table("player_points").select("league_id", *learn.KEY, "points")
    names = {r["league_id"]: r["name"].split()[0] for r in store.read_table("leagues", "raw").iter_rows(named=True)}
    scored = (
        proj.join(test, on=learn.KEY)
        .join(points, on=["league_id", *learn.KEY], how="left")
        .with_columns(
            pl.col("points").fill_null(0.0).alias("actual"),
            pl.col("league_id").replace_strict(names).alias("league"),
        )
    )
    print(f"scored rows {scored.height} (projection made for every universe row; "
          f"{int((~scored['has_history']).sum())} with no earlier game get the model's output on empty lags)")
    for cand in ("statline", "snaps_q"):
        out = []
        for label, mask in (("report-listed", flagged), ("all", pl.lit(True))):
            for (league,), g in scored.filter(mask).group_by("league"):
                out.append({"rows": label, "league": league, "season": "all", "pos": "ALL", **score(g, cand)})
                for (s,), gs in g.group_by("season"):
                    out.append({"rows": label, "league": league, "season": str(s), "pos": "ALL", **score(gs, cand)})
                for (p,), gp in g.group_by("position"):
                    out.append({"rows": label, "league": league, "season": "all", "pos": p, **score(gp, cand)})
        print(f"\n-- candidate {cand} against snaps")
        print(pl.DataFrame(out).sort("rows", "league", "pos", "season"))


if __name__ == "__main__":
    main()
