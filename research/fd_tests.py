"""Nine tests of what an outside weekly projection (FantasyData) tells us about our own.

Every fitted number is scored leave-one-season-out over 2019 to 2021: fit on two seasons, score
the third. Rows are player-weeks where the player played, both projections exist and their
average is above MIN_PROJECTION; our projection is the size-calibrated baseline. Tests 1 to 5, 7
and 9 use Colgate's scoring (test 6 compares both leagues).

1 blend weight by segment            4 disagreement as a volatility signal   7 bias by projection size
2 information or just scale          5 volume versus efficiency              8 team-score spread
3 early-season cold start            6 scoring-specific weights              9 game-script context

Build the panel first: uv run python research/fd_panel.py
Run from the repo root: uv run python research/fd_tests.py
"""

import math

import numpy as np
import polars as pl
from fd_panel import SCRATCH

from fantasy import store
from fantasy.sim.lineup import Player, auto_lineup, lineup_slots
from fantasy.sim.odds import lineup_moments

SEASONS = (2019, 2020, 2021)
MIN_PROJECTION = 3.0
BLEND_W = 0.8  # weight on FantasyData where a fixed blend is needed (test 1 finds about 0.8)
N_TEAMS, ROUNDS = 10, 12
Z80 = 1.2815515655446004
ROLES = ["QB1", "RB1", "RB2", "WR1", "WR2", "WR3", "TE1"]


def load() -> pl.DataFrame:
    panel = pl.read_parquet(SCRATCH / "fd_panel.parquet")
    rows = panel.filter(
        pl.col("played") & pl.col("ours").is_not_null() & pl.col("fd").is_not_null()
    ).with_columns(((pl.col("ours") + pl.col("fd")) / 2).alias("avg"))
    rows = rows.filter(pl.col("avg") > MIN_PROJECTION)
    share = pl.col("avg").rank("ordinal").over("league_key", "position") / pl.len().over(
        "league_key", "position"
    )
    week = pl.col("week")
    return rows.with_columns(
        (share * 3).floor().clip(0, 2).cast(pl.Int64).alias("tier"),
        pl.when(week <= 2).then(pl.lit("w01-02"))
        .when(week <= 4).then(pl.lit("w03-04"))
        .when(week <= 8).then(pl.lit("w05-08"))
        .when(week <= 13).then(pl.lit("w09-13"))
        .otherwise(pl.lit("w14-17"))
        .alias("weeks"),
        pl.col("has_history").fill_null(False).cast(pl.String).alias("history"),
    )


def rmse(err: np.ndarray) -> float:
    return float(np.sqrt(np.mean(err**2)))


def best_weight(a: np.ndarray, o: np.ndarray, f: np.ndarray) -> float:
    """Weight on f that minimizes squared error of (1 - w) o + w f against a, kept in [0, 1]."""
    d = f - o
    den = float((d * d).sum())
    return float(np.clip(((a - o) * d).sum() / den, 0.0, 1.0)) if den > 0 else 0.0


def arrays(df: pl.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return df["actual"].to_numpy(), df["ours"].to_numpy(), df["fd"].to_numpy()


def loso_blend(df: pl.DataFrame, by: list[str]) -> float:
    """Out-of-sample RMSE of a blend whose weight is fit per group on the other seasons."""
    errors = []
    for season in SEASONS:
        train, test = df.filter(pl.col("season") != season), df.filter(pl.col("season") == season)
        overall = best_weight(*arrays(train))
        weights = {k: best_weight(*arrays(g)) for k, g in train.group_by(by)} if by else {}
        for key, g in test.group_by(by) if by else [((), test)]:
            a, o, f = arrays(g)
            w = weights.get(key, overall)
            errors.append(a - (o + w * (f - o)))
    return rmse(np.concatenate(errors))


def show(title: str, frame: pl.DataFrame) -> None:
    print(f"\n== {title}")
    with pl.Config(tbl_rows=40, tbl_cols=14, tbl_width_chars=160):
        print(frame)


def test1_and_3(df: pl.DataFrame) -> None:
    a, o, f = arrays(df)
    print(
        f"all: n={df.height}  RMSE ours {rmse(a - o):.3f}  FantasyData {rmse(a - f):.3f}  "
        f"best weight on FantasyData {best_weight(a, o, f):.2f}  out-of-sample blend "
        f"{loso_blend(df, []):.3f}  at 0.5 {rmse(a - (o + f) / 2):.3f}"
    )
    for by in (["position"], ["tier"], ["weeks"], ["history"], ["season"], ["position", "weeks"]):
        rows = []
        for key, g in df.group_by(by, maintain_order=True):
            ga, go, gf = arrays(g)
            rows.append(
                {
                    **dict(zip(by, key, strict=True)),
                    "n": g.height,
                    "ours": round(rmse(ga - go), 3),
                    "fd": round(rmse(ga - gf), 3),
                    "gap_pct": round(100 * (rmse(ga - go) - rmse(ga - gf)) / rmse(ga - go), 1),
                    "w_star": round(best_weight(ga, go, gf), 2),
                }
            )
        sort = by if by != ["position", "weeks"] else by
        show(f"1/3 blend weight by {', '.join(by)}", pl.DataFrame(rows).sort(sort))
        if by != ["season"]:  # a held-out season has no training group of its own
            print(
                f"   out-of-sample RMSE, weight fit per {'/'.join(by)}: {loso_blend(df, by):.3f} "
                f"(one weight for all: {loso_blend(df, []):.3f})"
            )


def test2(df: pl.DataFrame) -> None:
    a, o, f = arrays(df)
    x = np.column_stack([np.ones(len(a)), o, f])
    inv = np.linalg.inv(x.T @ x)
    beta = inv @ x.T @ a
    e = a - x @ beta
    cov = inv @ (x.T * e**2) @ x @ inv * len(a) / (len(a) - 3)
    se = np.sqrt(np.diag(cov))
    print("\n== 2 actual = c + b1 ours + b2 FantasyData (robust standard errors)")
    for name, b, s in zip(("c", "b1 ours", "b2 fd"), beta, se, strict=True):
        print(f"   {name:8s} {b:+.3f}  (se {s:.3f})")
    print(f"   b1 + b2 = {beta[1] + beta[2]:.3f}: below 1 means projections are too large on average")
    d = f - o
    slope = float(((a - o) * d).sum() / (d * d).sum())
    print(f"   miss of ours on (fd - ours): slope {slope:.3f} (share of the gap that is real signal)")


def test4(df: pl.DataFrame) -> None:
    a, o, f = arrays(df)
    m = o + BLEND_W * (f - o)
    avg = df["avg"].to_numpy()
    work = df.with_columns(
        pl.Series("res", a - m),
        pl.Series("rel", (a - m) / avg),
        pl.Series("gap", np.abs(f - o) / avg),
    )
    share = pl.col("gap").rank("ordinal").over("position") / pl.len().over("position")
    work = work.with_columns((share * 3).floor().clip(0, 2).cast(pl.Int64).alias("gap_tier"))
    rho = work.select(pl.corr("gap", pl.col("rel").abs(), method="spearman")).item()
    print(f"\n== 4 disagreement as a volatility signal: Spearman(|gap|, |miss|) = {rho:+.3f}")
    show(
        "4 miss size by disagreement tercile (relative to the projection)",
        work.group_by("gap_tier")
        .agg(pl.len().alias("n"), pl.col("rel").pow(2).mean().sqrt().round(3).alias("cv"))
        .sort("gap_tier"),
    )

    def held_out_nll(cells: list[str]) -> float:
        total, n = 0.0, 0
        for season in SEASONS:
            train, test = work.filter(pl.col("season") != season), work.filter(pl.col("season") == season)
            cv = {
                k: math.sqrt(float(g["rel"].pow(2).mean()))
                for k, g in train.group_by(cells)
            }
            for key, g in test.group_by(cells):
                sd = g["avg"].to_numpy() * cv[key]
                res = g["res"].to_numpy()
                total += float((np.log(sd) + 0.5 * (res / sd) ** 2).sum())
                n += g.height
        return total / n

    base = held_out_nll(["position", "tier"])
    withgap = held_out_nll(["position", "tier", "gap_tier"])
    print(f"   held-out mean NLL: spread by size {base:.4f}, plus disagreement {withgap:.4f} "
          f"(lower is better; difference {withgap - base:+.4f})")


def volume(prefix: str, position: str) -> pl.Expr:
    """The opportunity count that drives a position's points, from stats named with `prefix`."""
    if position == "QB":
        return pl.col(f"{prefix}attempts") + pl.col(f"{prefix}carries")
    if position == "RB":
        return pl.col(f"{prefix}carries") + pl.col(f"{prefix}targets")
    return pl.col(f"{prefix}targets")


def test5(df: pl.DataFrame) -> None:
    rows = []
    for position in ("QB", "RB", "WR", "TE"):
        g = df.filter(pl.col("position") == position)
        fd_volume = (
            pl.col("passing_att") + pl.col("rushing_att")
            if position == "QB"
            else pl.col("rushing_att") + pl.col("receiving_tgts")
            if position == "RB"
            else pl.col("receiving_tgts")
        )
        g = g.with_columns(
            fd_volume.alias("v_fd"),
            volume("actual_", position).alias("v_act"),
            volume("trail_", position).alias("v_trail"),
        ).drop_nulls("v_trail").filter((pl.col("v_fd") > 0.5) & (pl.col("v_trail") > 0.5))
        a, o, f = arrays(g)
        v_fd, v_act, v_tr = (g[c].to_numpy() for c in ("v_fd", "v_act", "v_trail"))
        fd_at_trail = f * np.clip(v_tr / v_fd, 0.25, 4.0)
        ours_at_fd = o * np.clip(v_fd / v_tr, 0.25, 4.0)
        rows.append(
            {
                "position": position,
                "n": g.height,
                "volume_rmse_fd": round(rmse(v_act - v_fd), 2),
                "volume_rmse_trailing": round(rmse(v_act - v_tr), 2),
                "pts_ours": round(rmse(a - o), 3),
                "pts_fd": round(rmse(a - f), 3),
                "fd_with_trailing_volume": round(rmse(a - fd_at_trail), 3),
                "ours_with_fd_volume": round(rmse(a - ours_at_fd), 3),
            }
        )
    show("5 volume versus efficiency (RMSE; volume = carries, targets or attempts)", pl.DataFrame(rows))


def test6(df_all: pl.DataFrame) -> None:
    rows = []
    for league, g in df_all.group_by("league_key"):
        a, o, f = arrays(g)
        rows.append(
            {
                "league": league[0],
                "n": g.height,
                "ours": round(rmse(a - o), 3),
                "fd": round(rmse(a - f), 3),
                "w_star": round(best_weight(a, o, f), 2),
                "blend_oos": round(loso_blend(g, []), 3),
            }
        )
    show("6 scoring-specific weights (Colgate 1 PPR, YinzBurgh 0.5 PPR; the same players)", pl.DataFrame(rows))


def test7(df: pl.DataFrame) -> None:
    a, o, f = arrays(df)
    work = df.with_columns(pl.Series("blend", o + BLEND_W * (f - o)))
    rows = []
    for source in ("ours", "fd", "blend"):
        # each source is sorted by its own projection: sorting on a joint average would build in
        # a regression-to-the-mean pattern that looks like bias
        decile = (pl.col(source).rank("ordinal") / pl.len() * 10).ceil().clip(1, 10).cast(pl.Int64)
        for d, g in work.with_columns(decile.alias("decile")).group_by("decile"):
            rows.append(
                {
                    "source": source,
                    "decile": d[0],
                    "mean_proj": round(float(g[source].mean()), 1),
                    "bias": round(float(g["actual"].mean()) - float(g[source].mean()), 2),
                }
            )
    table = pl.DataFrame(rows).pivot(on="source", index="decile", values="bias").sort("decile")
    show("7 mean actual minus projection by each source's own projection decile (points a game)", table)


def build_teams(pool: pl.DataFrame) -> list[list[str]]:
    ranked = pool.sort("pred", descending=True)["gsis_id"].to_list()
    teams: list[list[str]] = [[] for _ in range(N_TEAMS)]
    for pick, pid in enumerate(ranked[: N_TEAMS * ROUNDS]):
        r, s = divmod(pick, N_TEAMS)
        teams[s if r % 2 == 0 else N_TEAMS - 1 - s].append(pid)
    return teams


def role_table(g: pl.DataFrame, col: str) -> pl.DataFrame:
    rank = pl.col(col).rank("ordinal", descending=True).over("season", "week", "team_code", "position")
    return g.with_columns((pl.col("position") + rank.cast(pl.String)).alias("role")).filter(
        pl.col("role").is_in(ROLES)
    )


def fit_spread(train: pl.DataFrame, col: str):
    """Pooled and size-tier spreads of the miss, and teammate correlations, for projection `col`."""
    work = train.with_columns((pl.col("actual") - pl.col(col)).alias("res"))
    cv, tiers = {}, {}
    for (position,), g in work.group_by("position"):
        x, r = g[col].to_numpy(), g["res"].to_numpy()
        cv[position] = float(np.sqrt((r**2).sum() / (x**2).sum()))
        edges = np.quantile(x, [1 / 3, 2 / 3])
        t = np.digitize(x, edges)
        cuts = (float(edges[0]), float(edges[1]), 1e9)
        tiers[position] = tuple(
            (cuts[k], float(np.sqrt((r[t == k] ** 2).sum() / (x[t == k] ** 2).sum()))) for k in range(3)
        )
    roled = role_table(work, col).select("season", "week", "team_code", "role", "res")
    other = roled.rename({"role": "role_b", "res": "res_b"})
    pairs = (
        roled.join(other, on=["season", "week", "team_code"])
        .filter(pl.col("role") < pl.col("role_b"))
        .group_by("role", "role_b")
        .agg(pl.corr("res", "res_b").alias("rho"), pl.len().alias("n"))
        .filter(pl.col("n") >= 100)
    )
    rho = {}
    for a_, b_, r_ in pairs.select("role", "role_b", "rho").iter_rows():
        rho[(a_, b_)] = rho[(b_, a_)] = r_
    return cv, tiers, rho


def test8(df: pl.DataFrame) -> None:
    league = store.read_table("leagues", "raw").filter(pl.col("league_key") == "colgate").row(0, named=True)
    slots = lineup_slots(list(league["roster_positions"]))
    work = df.with_columns((pl.col("ours") + BLEND_W * (pl.col("fd") - pl.col("ours"))).alias("blend"))
    results = {name: [] for name in ("ours", "fd", "blend")}
    for season in SEASONS:
        train, test = work.filter(pl.col("season") != season), work.filter(pl.col("season") == season)
        fits = {name: fit_spread(train, name) for name in results}
        for (_week,), pool in test.group_by("week"):
            pool = pool.with_columns(pl.col("blend").alias("pred"))
            by_id = {r["gsis_id"]: r for r in pool.iter_rows(named=True)}
            for team in build_teams(pool):
                started = auto_lineup(
                    [Player(i, by_id[i]["position"], by_id[i]["blend"]) for i in team], slots
                ).players
                actual = sum(by_id[i]["actual"] for i in started)
                for name, (cv, tiers, rho) in fits.items():
                    chosen = [Player(i, by_id[i]["position"], by_id[i][name]) for i in started]
                    mean, var, _ = lineup_moments(chosen, cv, rho, tiers)
                    results[name].append((actual, mean, math.sqrt(var)))
    rows = []
    for name, vals in results.items():
        arr = np.array(vals)
        z = (arr[:, 0] - arr[:, 1]) / arr[:, 2]
        rows.append(
            {
                "mean_from": name,
                "teams": len(arr),
                "team_rmse": round(rmse(arr[:, 0] - arr[:, 1]), 2),
                "model_sd": round(float(arr[:, 2].mean()), 2),
                "z_sd": round(float(z.std()), 3),
                "cov80": round(float((np.abs(z) <= Z80).mean()), 3),
            }
        )
    show("8 synthetic-league team totals with each source's mean and its own fitted spread", pl.DataFrame(rows))


def ols_loso(df: pl.DataFrame, target: str, cols: list[str]) -> float:
    errors = []
    for season in SEASONS:
        train, test = df.filter(pl.col("season") != season), df.filter(pl.col("season") == season)
        x = np.column_stack([np.ones(train.height)] + [train[c].to_numpy() for c in cols])
        beta = np.linalg.lstsq(x, train[target].to_numpy(), rcond=None)[0]
        xt = np.column_stack([np.ones(test.height)] + [test[c].to_numpy() for c in cols])
        errors.append(test[target].to_numpy() - xt @ beta)
    return rmse(np.concatenate(errors))


def test9(df: pl.DataFrame) -> None:
    # the same players feed every predictor: those who played and have both projections
    teams = (
        df.group_by("season", "week", "team_code")
        .agg(
            pl.col("fd").sum().alias("fd_sum"),
            pl.col("ours").sum().alias("ours_sum"),
            pl.col("actual").sum().alias("skill_actual"),
            pl.col("team_implied").first().alias("implied"),
            pl.col("points_for").first().alias("team_points"),
            pl.len().alias("n_players"),
        )
        .drop_nulls(["implied", "team_points", "ours_sum", "fd_sum"])
        .filter(pl.col("n_players") >= 6)
    )
    rows = []
    for target in ("team_points", "skill_actual"):
        for label, cols in (
            ("implied total", ["implied"]),
            ("FantasyData team sum", ["fd_sum"]),
            ("our team sum", ["ours_sum"]),
            ("implied + FantasyData", ["implied", "fd_sum"]),
            ("implied + ours", ["implied", "ours_sum"]),
        ):
            rows.append({"predicts": target, "from": label, "oos_rmse": round(ols_loso(teams, target, cols), 2)})
    show(f"9 game script: team-week predictors, out-of-sample ({teams.height} team-weeks)", pl.DataFrame(rows))
    work = df.with_columns(
        (pl.col("team_implied") / pl.col("team_implied").mean()).log().alias("log_implied"),
        pl.Series("blend", df["ours"].to_numpy() + BLEND_W * (df["fd"].to_numpy() - df["ours"].to_numpy())),
    ).drop_nulls("log_implied")
    print("   slope of (actual - projection)/projection on log(implied total / average): a nonzero slope")
    print("   means the game-script multiplier under- or over-reaches")
    clusters = (work["season"] * 100 + work["week"]).to_numpy()
    for col in ("ours", "fd", "blend"):
        # relative to the average projection, which is above MIN_PROJECTION for every row
        rel = ((work["actual"] - work[col]) / work["avg"]).to_numpy()
        x = work["log_implied"].to_numpy()
        xc = x - x.mean()
        slope = float((xc * (rel - rel.mean())).sum() / (xc * xc).sum())
        resid = rel - rel.mean() - slope * xc
        score = {c: float((xc[clusters == c] * resid[clusters == c]).sum()) for c in np.unique(clusters)}
        se = math.sqrt(sum(v * v for v in score.values())) / float((xc * xc).sum())
        print(f"   {col:6s} slope {slope:+.3f}  (se {se:.3f}, clustered by week)")


def main() -> None:
    panel = pl.read_parquet(SCRATCH / "fd_panel.parquet")
    both = load()
    df = both.filter(pl.col("league_key") == "colgate")
    test1_and_3(df)
    test2(df)
    test4(df)
    test5(df)
    test6(both)
    test7(df)
    test8(df)
    test9(df)


if __name__ == "__main__":
    main()
