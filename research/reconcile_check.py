"""Reconcile player projections with the Vegas team total (hierarchical forecast reconciliation,
Hyndman et al. 2011; MinT, Wickramasuriya et al. 2019).

The set S of a team-week is every QB, RB, WR and TE on that week's depth chart (`nfl_depth`, the
chart the learned model already uses as a feature), whether or not he then played: restricting it
to the players who recorded stats would use the result. A charted player with a learned row gets
his `proj_learned` value (recomputed here, must match); one without (he did not play) gets a
prediction from the same walk-forward model on the same features. His team is the week's team if
he played, else his latest earlier team; charted players with no game in the data are dropped.

T_hat = a + b * implied team total, fit per league on team-weeks of seasons before the scored one
(team skill points: every QB, RB, WR and TE row of `player_points`, regular season).
S = sum over the chart of p_play * p, where p_play is the share of charted players with the same
position, depth rank (4 and below pooled) and stat line in the team's previous game who recorded a
stat line, in seasons before the scored one (without it S runs about 29 points above the team's
points: backups the model projects as if they play). Candidates for a charted player with
projection p:
(a) scale: p * clip(T_hat / S) ** alpha, one alpha per league fit on protocol rows of 2021..s-1;
(b) MinT: bottom series are roles (QB1, QB2, RB1 to RB3, WR1 to WR5, TE1, TE2, OTHER on the chart,
    OUT = points of players not on the chart, forecast by its training mean), top = T_hat; W is
    the covariance of [top error, role errors] over 2021..s-1 team-weeks, shrunk toward its
    diagonal (Schafer-Strimmer intensity); b~ = (S'W^-1 S)^-1 S'W^-1 y^, bottoms in expected
    points. A role's change is split over its players by expected points and divided by p_play
    (a change in the projection given he plays), floored at 0.
Season 2021 has no earlier out-of-fold season, so it is left unchanged.

Scored on the `learn.compare_to_baseline` rows of 2024, 2025 and 2026; paired per-week t.
Writes the best candidate's projections for every past `proj_learned` row from 2021 to
PREDS_PATH (league_id, gsis_id, season, week, projection).

Run from the repo root: OMP_NUM_THREADS=3 uv run python research/reconcile_check.py
"""

import os
import sys
from pathlib import Path

import numpy as np
import polars as pl

sys.path.insert(0, str(Path(__file__).parent))
import wf_panel as w  # noqa: E402

from fantasy import store  # noqa: E402
from fantasy.stages.learn import (  # noqa: E402
    build_features,
    design,
    fit_predict,
    games_frame,
    load_extras,
    state_frame,
    train_seasons,
)
from fantasy.stages.project import expected_frame  # noqa: E402
from fantasy.store import SKILL, week_index  # noqa: E402

FIRST = 2021  # first season with a clean out-of-fold learned projection
SCORED = [2024, 2025, 2026]
TEAM_FROM = 2018
AVAIL_FROM = 2019  # first season whose charts estimate the chance a charted player plays
DEPTH_CAP = 4  # depth ranks from 4 down share one cell
RATIO_CLIP = (0.5, 2.0)  # guard against a chart with almost nobody on it
ALPHAS = np.round(np.linspace(-0.5, 1.5, 201), 3)
ROLE_DEPTH = {"QB": 2, "RB": 3, "WR": 5, "TE": 2}
NOISE = {"colgate": 0.04, "yinzburgh": 0.10}  # refit noise sd of the learned model, % of RMSE
TW = ["league_id", "season", "week", "team"]
ZERO_FILL = pl.col(pl.Float64).fill_null(0.0)  # a role nobody holds that week
PREDS_PATH = Path(
    os.environ.get(
        "RECONCILE_PREDS",
        "/private/tmp/claude-501/-Users-eliheakins-personal-fantasy-app/"
        "230639a7-242c-4003-bae2-a92998c4f96c/scratchpad/preds/reconcile.parquet",
    )
)


def charted(
    lid: str, exp: pl.DataFrame, depth: pl.DataFrame, games: pl.DataFrame, first: int = FIRST
) -> pl.DataFrame:
    """KEY, position, team for every skill player on a team-week chart from `first` on."""
    played = exp.filter(pl.col("league_id") == lid).select(
        "gsis_id", "season", "week", "team", "position"
    )
    chart = depth.filter(pl.col("season") >= first).unique(["gsis_id", "season", "week"])
    now = chart.join(played, on=["gsis_id", "season", "week"], how="left")
    known, unknown = now.filter(pl.col("team").is_not_null()), now.filter(pl.col("team").is_null())
    latest = (
        unknown.drop("team", "position")
        .with_columns(week_index().alias("t"))
        .sort("t")
        .join_asof(
            played.with_columns(week_index().alias("t")).drop("season", "week").sort("t"),
            on="t",
            by="gsis_id",
            strategy="backward",
            allow_exact_matches=False,
        )
        .drop("t")
    )
    team_weeks = games.filter(pl.col("game_type") == "REG").select("team", "season", "week")
    return (
        pl.concat([known, latest.select(known.columns)])
        .filter(pl.col("position").is_in(SKILL) & pl.col("team").is_not_null())
        .join(team_weeks, on=["team", "season", "week"])
        .with_columns(pl.lit(lid).alias("league_id"))
    )


def chart_projections() -> pl.DataFrame:
    """KEY, position, team, depth_rank, projection, played for every charted player (cached)."""
    path = w.SCRATCH / "reconcile_chart.parquet"
    if path.exists():
        return pl.read_parquet(path)
    leagues = store.read_table("leagues", "raw")
    opp = store.read_table("nfl_ff_opportunity", "raw")
    exp = expected_frame(opp, store.read_table("player_points"), leagues)
    games_all = games_frame(
        exp, opp, store.read_table("nfl_snaps", "raw"), store.read_table("nfl_player_stats", "raw")
    )
    lines = store.read_table("team_games")
    extras = load_extras()
    out, charts = [], []
    for lid in w.league_ids():
        panel = w.panel(lid)
        chart = charted(lid, exp, extras.depth, lines)
        charts.append(chart.select(w.KEY))
        extra = chart.join(panel.select(w.KEY), on=w.KEY, how="anti").select(
            *w.KEY, "position", "team"
        )
        state = state_frame(games_all.filter(pl.col("league_id") == lid))
        extra_x = build_features(extra, state, lines, extras, 1)
        available = sorted(panel["season"].unique().to_list())
        for season in range(FIRST, max(SCORED) + 1):
            train = panel.filter(pl.col("season").is_in(train_seasons(season, available)))
            test, more = (
                panel.filter(pl.col("season") == season),
                extra_x.filter(pl.col("season") == season),
            )
            x_test = np.vstack([design(test, True), design(more, True)])
            pred = fit_predict(design(train, True), train["points"].to_numpy(), x_test)
            rows = pl.concat(
                [
                    test.select(*w.KEY, "position", "team").with_columns(played=pl.lit(True)),
                    more.select(*w.KEY, "position", "team").with_columns(played=pl.lit(False)),
                ]
            ).with_columns(pl.Series("projection", pred))
            out.append(rows)
            print(f"{w.LEAGUE_NAMES[lid]} {season}: {test.height} played, {more.height} chart-only")
    allp = pl.concat(out)
    stored = store.read_table("proj_learned").filter(~pl.col("is_future"))
    both = allp.filter("played").join(
        stored.select(*w.KEY, pl.col("projection").alias("s")), on=w.KEY
    )
    print(
        f"reproduction: {both.height} rows, "
        f"max abs diff {(both['projection'] - both['s']).abs().max()}"
    )
    keys = pl.concat(charts).unique().with_columns(on_chart=pl.lit(True))
    result = allp.join(keys, on=w.KEY, how="left").with_columns(pl.col("on_chart").fill_null(False))
    result.write_parquet(path)
    return result


def chart_flags() -> pl.DataFrame:
    """KEY, position, depth cell, played, prev_played (a stat row in his team's previous game)
    for every charted skill player from AVAIL_FROM (cached)."""
    path = w.SCRATCH / "reconcile_flags.parquet"
    if path.exists():
        return pl.read_parquet(path)
    leagues = store.read_table("leagues", "raw")
    exp = expected_frame(
        store.read_table("nfl_ff_opportunity", "raw"), store.read_table("player_points"), leagues
    )
    depth = store.read_table("nfl_depth", "raw").unique(["gsis_id", "season", "week"])
    games = store.read_table("team_games")
    prev = (
        games.filter(pl.col("game_type") == "REG")
        .sort("team", "season", "week")
        .with_columns(
            prev_season=pl.col("season").shift(1).over("team"),
            prev_week=pl.col("week").shift(1).over("team"),
        )
        .select("team", "season", "week", "prev_season", "prev_week")
    )
    out = []
    for lid in w.league_ids():
        seen = (
            exp.filter(pl.col("league_id") == lid)
            .select("gsis_id", "season", "week")
            .unique()
            .with_columns(flag=pl.lit(True))
        )
        c = (
            charted(lid, exp, depth, games, AVAIL_FROM)
            .join(
                depth.select("gsis_id", "season", "week", "depth_rank"),
                on=["gsis_id", "season", "week"],
            )
            .join(seen, on=["gsis_id", "season", "week"], how="left")
            .join(prev, on=["team", "season", "week"], how="left")
            .join(
                seen.rename({"season": "prev_season", "week": "prev_week", "flag": "prev_flag"}),
                on=["gsis_id", "prev_season", "prev_week"],
                how="left",
            )
        )
        out.append(
            c.select(
                *w.KEY,
                "position",
                cell=pl.col("depth_rank").fill_null(DEPTH_CAP).clip(1, DEPTH_CAP).cast(pl.Int64),
                played=pl.col("flag").fill_null(False),
                prev_played=pl.col("prev_flag").fill_null(False),
            )
        )
    result = pl.concat(out)
    result.write_parquet(path)
    return result


def with_play_chance(chart: pl.DataFrame) -> pl.DataFrame:
    """p_play: share of charted players with the same position, depth cell and previous-game
    flag who recorded a stat line, in seasons before the row's season (from AVAIL_FROM)."""
    flags = chart_flags()
    cell = ["league_id", "position", "cell", "prev_played"]
    keyed = chart.join(flags.select(*w.KEY, "cell", "prev_played"), on=w.KEY, how="left")
    parts = []
    for (season,), g in keyed.group_by("season"):
        rates = (
            flags.filter(pl.col("season") < season)
            .group_by(cell)
            .agg(pl.col("played").mean().alias("p_play"))
        )
        parts.append(g.join(rates, on=cell, how="left"))
    return pl.concat(parts).with_columns(pl.col("p_play").fill_null(0.5))


def team_actual() -> pl.DataFrame:
    """TW, actual team skill points, implied team total (regular season, from TEAM_FROM)."""
    pts = store.read_table("player_points").filter(
        (pl.col("season_type") == "REG") & pl.col("position").is_in(SKILL)
    )
    tot = pts.group_by(TW).agg(pl.col("points").sum().alias("t_actual"))
    lines = store.read_table("team_games").filter(pl.col("game_type") == "REG")
    return tot.join(
        lines.select("team", "season", "week", "team_implied"), on=["team", "season", "week"]
    ).filter(pl.col("team_implied").is_not_null() & (pl.col("season") >= TEAM_FROM))


def with_t_hat(teams: pl.DataFrame) -> pl.DataFrame:
    """t_hat (linear) and t_hat_log (log-linear, smeared) from seasons before each row's season."""
    parts = []
    for (lid, season), g in teams.group_by("league_id", "season"):
        if season <= TEAM_FROM:
            continue
        fit = teams.filter((pl.col("league_id") == lid) & (pl.col("season") < season))
        x, y = fit["team_implied"].to_numpy(), fit["t_actual"].to_numpy()
        b, a = np.polyfit(x, y, 1)
        bl, al = np.polyfit(np.log(x), np.log(np.maximum(y, 1.0)), 1)
        smear = float(np.mean(np.exp(np.log(np.maximum(y, 1.0)) - (al + bl * np.log(x)))))
        xi = g["team_implied"].to_numpy()
        parts.append(
            g.with_columns(
                pl.Series("t_hat", a + b * xi),
                pl.Series("t_hat_log", smear * np.exp(al + bl * np.log(xi))),
            )
        )
    return pl.concat(parts)


def roles(chart: pl.DataFrame) -> pl.DataFrame:
    rank = pl.col("expected").rank("ordinal", descending=True).over(*TW, "position")
    limit = pl.col("position").replace_strict(ROLE_DEPTH, return_dtype=pl.Int64)
    return chart.with_columns(
        role=pl.when(rank <= limit)
        .then(pl.col("position") + rank.cast(pl.String))
        .otherwise(pl.lit("OTHER"))
    )


ROLE_NAMES = [f"{p}{i}" for p, n in ROLE_DEPTH.items() for i in range(1, n + 1)] + ["OTHER", "OUT"]


def shrink(errors: np.ndarray) -> np.ndarray:
    """Covariance shrunk toward its diagonal with the Schafer-Strimmer intensity."""
    n = errors.shape[0]
    x = errors - errors.mean(axis=0)
    sd = x.std(axis=0, ddof=1)
    sd[sd == 0] = 1.0
    z = x / sd
    wk = z[:, :, None] * z[:, None, :]
    r = wk.mean(axis=0) * n / (n - 1)
    var_r = wk.var(axis=0) * n**2 / (n - 1) ** 3
    off = ~np.eye(z.shape[1], dtype=bool)
    lam = float(np.clip(var_r[off].sum() / (r[off] ** 2).sum(), 0.0, 1.0))
    cov = np.cov(x, rowvar=False)
    return lam * np.diag(np.diag(cov)) + (1 - lam) * cov


def mint_projection(w_mat: np.ndarray) -> np.ndarray:
    """P with bottom~ = P @ [top^, bottom^], for one top that is the sum of the k bottoms."""
    k = w_mat.shape[0] - 1
    s = np.vstack([np.ones((1, k)), np.eye(k)])
    w_inv = np.linalg.inv(w_mat)
    return np.linalg.solve(s.T @ w_inv @ s, s.T @ w_inv)


def build() -> tuple[pl.DataFrame, pl.DataFrame]:
    """(players, team_weeks): every past proj_learned row from FIRST with points and chart info,
    and the chart-level team-week frame."""
    chart = roles(
        with_play_chance(chart_projections().filter("on_chart")).with_columns(
            expected=pl.col("p_play") * pl.col("projection")
        )
    )
    pts = store.read_table("player_points").select(*w.KEY, "points")
    chart = chart.join(pts, on=w.KEY, how="left").with_columns(pl.col("points").fill_null(0.0))
    teams = with_t_hat(team_actual())
    tw = (
        chart.group_by(TW)
        .agg(pl.col("expected").sum().alias("s"), pl.col("points").sum().alias("s_actual"))
        .join(teams, on=TW)
        .with_columns((pl.col("t_actual") - pl.col("s_actual")).alias("OUT"))
    )
    role_err = (
        chart.with_columns((pl.col("points") - pl.col("expected")).alias("e"))
        .group_by(*TW, "role")
        .agg(pl.col("e").sum(), pl.col("expected").sum().alias("role_proj"))
    )
    learned = store.read_table("proj_learned").filter(
        ~pl.col("is_future") & (pl.col("season") >= FIRST)
    )
    players = (
        learned.select(*w.KEY, "position", "team", pl.col("projection").alias("learned"))
        .join(pts, on=w.KEY)
        .join(
            chart.select(*w.KEY, "role", "expected", pl.col("projection").alias("chart_proj")),
            on=w.KEY,
            how="left",
        )
    )
    return players.join(tw.select(*TW, "s", "t_hat"), on=TW, how="left"), tw.join(
        role_err.pivot(on="role", index=TW, values="e").with_columns(ZERO_FILL), on=TW
    ).join(
        role_err.pivot(on="role", index=TW, values="role_proj")
        .with_columns(ZERO_FILL)
        .rename({r: f"p_{r}" for r in ROLE_NAMES if r != "OUT"}, strict=False),
        on=TW,
    )


def ratio() -> pl.Expr:
    """T_hat / S for a charted player; 1 for a player off the chart (left unchanged)."""
    r = (pl.col("t_hat") / pl.col("s")).clip(*RATIO_CLIP)
    return pl.when(pl.col("role").is_not_null()).then(r).otherwise(1.0).fill_null(1.0)


def fit_alpha(rows: pl.DataFrame) -> float:
    y, p, r = rows["points"].to_numpy(), rows["learned"].to_numpy(), rows["r"].to_numpy()
    sse = [float(((y - p * r**a) ** 2).sum()) for a in ALPHAS]
    return float(ALPHAS[int(np.argmin(sse))])


def candidate_a(players: pl.DataFrame, protocol: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    players = players.with_columns(r=ratio())
    prot = protocol.join(players.select(*w.KEY, "r"), on=w.KEY)
    out, alphas = [], {}
    for (lid, season), g in players.group_by("league_id", "season"):
        train = prot.filter((pl.col("league_id") == lid) & (pl.col("season") < season))
        alpha = fit_alpha(train) if train.height else 0.0
        alphas[(lid, season)] = alpha
        out.append(g.with_columns((pl.col("learned") * pl.col("r") ** alpha).alias("recon_a")))
    return pl.concat(out).drop("r"), alphas


def candidate_b(players: pl.DataFrame, tw: pl.DataFrame) -> tuple[pl.DataFrame, dict, pl.DataFrame]:
    bottoms = [r for r in ROLE_NAMES if r in tw.columns]
    adjust, lams = [], {}
    for (lid, season), g in tw.group_by("league_id", "season"):
        train = tw.filter(
            (pl.col("league_id") == lid) & (pl.col("season") < season) & (pl.col("season") >= FIRST)
        )
        if train.height == 0:
            continue
        out_mean = float(train["OUT"].mean())  # type: ignore[arg-type]
        top_err = (train["t_actual"] - train["t_hat"]).to_numpy()[:, None]
        errs = train.select(bottoms).to_numpy()
        errs[:, bottoms.index("OUT")] -= out_mean
        p_mat = mint_projection(shrink(np.hstack([top_err, errs])))
        base = np.column_stack(
            [g[f"p_{r}"].to_numpy() if r != "OUT" else np.full(g.height, out_mean) for r in bottoms]
        )
        recon = np.hstack([g["t_hat"].to_numpy()[:, None], base]) @ p_mat.T
        delta = recon - base
        lams[(w.LEAGUE_NAMES[lid], season)] = round(float(p_mat[bottoms.index("QB1"), 0]), 4)
        frame = g.select(TW).with_columns(
            pl.Series("s_b", recon[:, [j for j, r in enumerate(bottoms) if r != "OUT"]].sum(axis=1))
        )
        for j, r in enumerate(bottoms):
            if r != "OUT":
                frame = frame.with_columns(pl.Series(f"d_{r}", delta[:, j]))
        adjust.append(frame)
    adj = pl.concat(adjust)
    long = (
        adj.drop("s_b")
        .unpivot(index=TW, variable_name="role", value_name="delta")
        .with_columns(pl.col("role").str.strip_prefix("d_"))
    )
    role_proj = (
        players.filter(pl.col("role").is_not_null())
        .group_by(*TW, "role")
        .agg(pl.col("expected").sum().alias("role_sum"))
    )
    out = (
        players.join(long, on=[*TW, "role"], how="left")
        .join(role_proj, on=[*TW, "role"], how="left")
        .with_columns(
            recon_b=(
                pl.col("learned")
                + pl.col("delta").fill_null(0.0) * pl.col("chart_proj") / pl.col("role_sum")
            )
            .fill_null(pl.col("learned"))
            .clip(0.0, None)
        )
        .drop("delta", "role_sum")
    )
    return out, lams, adj.select(*TW, "s_b")


def verdict(rep: pl.DataFrame, cand: str) -> str:
    rows = rep.filter(pl.col("cand") == cand)
    pooled = rows.filter(pl.col("slice") == "all")
    seasons = rows.filter(pl.col("slice").str.starts_with("s"))
    lower = bool((pooled["rmse"] < pooled["rmse_ref"]).all())
    t_ok = bool((pooled["t"] >= 2).any())
    season_ok = bool((seasons["t"] > -1).all())
    noise_ok = all(g > 2 * NOISE[lg] for lg, g in pooled.select("league", "gain_pct").iter_rows())
    ok = lower and t_ok and season_ok and noise_ok
    return (
        f"{cand}: lower RMSE both {lower}, pooled t>=2 {t_ok}, no season t<=-1 {season_ok}, "
        f"gain >2x noise {noise_ok} -> {'SHIP' if ok else 'do not ship'}"
    )


def team_sums(tw: pl.DataFrame, alphas: dict, adj: pl.DataFrame) -> pl.DataFrame:
    """Team-sum RMSE against actual team skill points on the scored seasons: T_hat, the chart sum
    S before and after each reconciliation (the off-chart players' points are not in S)."""
    alpha = pl.DataFrame(
        [(lid, season, a) for (lid, season), a in alphas.items()],
        schema=["league_id", "season", "alpha"],
        orient="row",
    )
    frame = (
        tw.filter(pl.col("season").is_in(SCORED))
        .join(alpha, on=["league_id", "season"])
        .join(adj, on=TW)
        .with_columns(
            s_a=pl.col("s") * (pl.col("t_hat") / pl.col("s")).clip(*RATIO_CLIP) ** pl.col("alpha")
        )
    )
    rows = []
    for (lid,), g in frame.group_by("league_id"):
        y = g["t_actual"].to_numpy()
        for name in ("t_hat", "t_hat_log", "s", "s_a", "s_b"):
            e = y - g[name].to_numpy()
            rows.append(
                {
                    "league": w.LEAGUE_NAMES[lid],
                    "predictor": name,
                    "n": g.height,
                    "rmse": round(float(np.sqrt((e**2).mean())), 3),
                    "mean_err": round(float(-e.mean()), 3),
                }
            )
    return pl.DataFrame(rows).sort("league", "predictor")


def main() -> None:
    w.league_ids()  # fills the league names
    players, tw = build()
    protocol = w.scored_rows(
        players.select(*w.KEY, "position", "points", "learned"), w.calibrated_baseline(FIRST)
    )
    players, alphas = candidate_a(players, protocol)
    players, lams, adj = candidate_b(players, tw)
    print("alpha by league-season:", {(w.LEAGUE_NAMES[k[0]], k[1]): a for k, a in alphas.items()})
    print("MinT weight of QB1 on the top forecast:", lams)
    scored = w.scored_rows(
        players.filter(pl.col("season").is_in(SCORED)).select(
            *w.KEY, "position", "points", "learned", "recon_a", "recon_b"
        ),
        w.calibrated_baseline(FIRST),
    )
    rep = w.report(scored, ["recon_a", "recon_b"])
    with pl.Config(tbl_rows=60, tbl_cols=12):
        print(rep)
        print(team_sums(tw, alphas, adj))
    for cand in ("recon_a", "recon_b"):
        print(verdict(rep, cand))
    pooled = rep.filter(pl.col("slice") == "all").group_by("cand").agg(pl.col("gain_pct").mean())
    best = pooled.sort("gain_pct", descending=True)["cand"][0]
    PREDS_PATH.parent.mkdir(parents=True, exist_ok=True)
    players.select(
        "league_id", "gsis_id", "season", "week", pl.col(best).alias("projection")
    ).write_parquet(PREDS_PATH)
    print(f"wrote {best} for {players.height} rows to {PREDS_PATH}")


if __name__ == "__main__":
    main()
