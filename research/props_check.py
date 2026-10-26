"""Do player prop lines add information to the learned projection? (free archive, 2024 held out)

Data: the free archive https://github.com/firstandthirty/nfl-tools (player_props/data, no licence
file; the user ruled that data whose terms do not forbid scraping and storage may be used).
Download it into research/scratch/ (gitignored), never commit it, never run its code:
    git clone --depth 1 --filter=blob:none --sparse \
        https://github.com/firstandthirty/nfl-tools.git research/scratch/nfl-tools-dl/repo
    git -C research/scratch/nfl-tools-dl/repo sparse-checkout set player_props
Only its prop-line files are read (FanDuel lines from The Odds API history), not its PFF or
FantasyPros files.

Rule (fixed before looking at results). Rows: `bias_check.protocol_rows` with `protocol` true
(has history, size-calibrated baseline above 3), 2024, weeks 2 to 17, that are covered: QB has a
passing-yards line, RB a rushing-yards line, WR and TE both receptions and receiving-yards lines.
  prop mean per market: de-vig p_over = q_o / (q_o + q_u); yardage lines are medians, mean =
    r_m * (L + z * sigma_m) with z = Phi^-1(p_over) clamped to +/-1; receptions lambda from
    Poisson inversion of P(X > L) = p_over, mean = r_m * lambda. r_m and sigma_m from earlier data
    only: passing yards and receptions from the 2023 archive lines; rushing and receiving yards
    (no 2023 lines in the archive) from 2024 weeks before the scored week, so week 1 is not scored.
  X (prop-implied non-TD points) = league weights times the prop means for the four stats, the
    player's mean of a stat over his previous 8 games where that stat has no line.
  F (prop-implied points) = X + the player's mean over his previous 8 games of every other point
    (touchdowns, interceptions, fumbles, two-point conversions).
  Pass if, in both leagues, (a) OLS actual ~ 1 + learned + X has |t| >= 2 on X with standard
  errors clustered by game, and (b) the blend 0.5 learned + 0.5 F has lower RMSE than learned on
  covered rows with paired per-week |t| >= 2.
A three-way blend with Sleeper cannot be tested historically: Sleeper's past projections are
re-stamped after games (decisions.md, 2026-10-23).

Run from the repo root: OMP_NUM_THREADS=3 uv run python research/props_check.py [archive dir]
"""

import json
import re
import sys
from pathlib import Path

import numpy as np
import polars as pl
from scipy.optimize import brentq
from scipy.special import gammaincc
from scipy.stats import norm

import bias_check
from fantasy import store

ARCHIVE = Path("research/scratch/nfl-tools-dl/repo/player_props/data")
TEST_FILE = "processed/merged_props_with_context.csv"  # 2024, all four markets
FIT_FILES = ("processed/fanduel_pass_yds_history.csv", "processed/fanduel_receptions_history.csv")
FIT_SEASON = 2023
TEST_SEASON = 2024
FIRST_WEEK = 2  # week 1 has no earlier 2024 lines to fit rushing and receiving yards on
Z_CLAMP = 1.0
LAG_GAMES = 8
MIN_T = 2.0
# market -> (nflverse stat, Sleeper scoring key)
MARKETS = {
    "player_pass_yds": ("passing_yards", "pass_yd"),
    "player_rush_yds": ("rushing_yards", "rush_yd"),
    "player_receptions": ("receptions", "rec"),
    "player_reception_yds": ("receiving_yards", "rec_yd"),
}
YARDAGE = ("player_pass_yds", "player_rush_yds", "player_reception_yds")
FIT_ON_2023 = ("player_pass_yds", "player_receptions")
PRIMARY = {
    "QB": ["player_pass_yds"],
    "RB": ["player_rush_yds"],
    "WR": ["player_receptions", "player_reception_yds"],
    "TE": ["player_receptions", "player_reception_yds"],
}
KEYS = ["league_id", "gsis_id", "season", "week"]
SUFFIX = re.compile(r"\b(jr|sr|ii|iii|iv|v)\b")


def implied(price: pl.Expr) -> pl.Expr:
    """Implied probability of an American (|price| >= 100) or decimal price."""
    return (
        pl.when(price <= -100)
        .then(-price / (-price + 100))
        .when(price >= 100)
        .then(100 / (price + 100))
        .otherwise(1 / price)
    )


def norm_name(name: pl.Expr) -> pl.Expr:
    lowered = name.str.to_lowercase().str.replace_all(r"[.'\-]", "")
    return lowered.str.replace_all(SUFFIX.pattern, "").str.replace_all(r"\s+", " ").str.strip_chars()


def poisson_lambda(line: float, p_over: float) -> float:
    """lambda with P(X > line) = p_over; P(X <= k - 1) = Q(k, lambda) for k = floor(line) + 1
    (was ceil(line), off by one for an integer line; fixed 2026-10-26)."""
    k = int(np.floor(line)) + 1
    return float(brentq(lambda lam: gammaincc(k, lam) - (1 - p_over), 1e-6, 60.0))


def self_check() -> None:
    assert abs(poisson_lambda(3.5, 1 - gammaincc(4, 4.2)) - 4.2) < 1e-6
    probs = pl.DataFrame({"p": [-110.0, 1.91, 150.0]}).select(implied(pl.col("p")))["p"]
    assert np.allclose(probs.to_list(), [110 / 210, 1 / 1.91, 0.4])
    rng = np.random.default_rng(0)
    x = rng.normal(size=(400, 2))
    groups = np.repeat(np.arange(100), 4)
    y = 1 + x @ np.array([0.5, 0.0]) + rng.normal(size=400)
    _, t = clustered_ols(y, x, groups)
    assert abs(t[1]) > 5 and abs(t[2]) < 3


def team_abbr(archive: Path) -> dict[str, str]:
    d = pl.read_csv(archive / TEST_FILE, infer_schema_length=0)
    pairs = pl.concat(
        [
            d.select(pl.col("home_team").alias("n"), pl.col("home_team_abbr").alias("a")),
            d.select(pl.col("away_team").alias("n"), pl.col("away_team_abbr").alias("a")),
        ]
    ).unique()
    return dict(pairs.drop_nulls().iter_rows())


def load_lines(path: Path, abbr: dict[str, str], schedule: pl.DataFrame) -> pl.DataFrame:
    """One row per game, player and market (the last snapshot), with p_over, season and week."""
    snap = "actual_snapshot_time" if "actual_snapshot_time" in pl.read_csv(path, n_rows=1).columns else "requested_snapshot_time"
    d = pl.read_csv(path, infer_schema_length=0).filter(pl.col("market_key").is_in(list(MARKETS)))
    d = d.select(
        "event_id", "commence_time", "home_team", "away_team", "bookmaker_key", "market_key",
        "player", "line", "over_price", "under_price", snap,
    ).with_columns(
        pl.col("line", "over_price", "under_price").cast(pl.Float64),
        kick=pl.col("commence_time").str.to_datetime(time_zone="UTC"),
        snap=pl.col(snap).str.to_datetime(time_zone="UTC"),
        home=pl.col("home_team").replace_strict(abbr, default=None),
        away=pl.col("away_team").replace_strict(abbr, default=None),
    ).with_columns(
        lead_min=(pl.col("kick") - pl.col("snap")).dt.total_minutes(),
        gameday=pl.col("kick").dt.convert_time_zone("America/New_York").dt.strftime("%Y-%m-%d"),
        q_o=implied(pl.col("over_price")),
        q_u=implied(pl.col("under_price")),
        name=norm_name(pl.col("player")),
    )
    d = d.sort("snap").group_by("event_id", "name", "market_key").last()
    games = schedule.select(
        "gameday", pl.col("home_team").alias("home"), pl.col("away_team").alias("away"),
        "season", "week", "game_id",
    )
    return d.join(games, on=["gameday", "home", "away"]).with_columns(
        p_over=pl.col("q_o") / (pl.col("q_o") + pl.col("q_u"))
    )


def match_players(lines: pl.DataFrame, stats: pl.DataFrame) -> pl.DataFrame:
    """Attach gsis_id and the actual stat by name within the game's two teams (inner join, so a
    player with a line and no stat row, usually one who did not play, drops out)."""
    s = stats.select(
        pl.col("player_id").alias("gsis_id"), "season", "week", "team",
        norm_name(pl.col("player_display_name")).alias("name"),
        *[pl.col(stat) for stat, _ in MARKETS.values()],
    )
    both = pl.concat(
        [lines.join(s, left_on=["season", "week", side, "name"], right_on=["season", "week", "team", "name"]) for side in ("home", "away")],
        how="diagonal_relaxed",
    )
    actual = pl.coalesce(
        [pl.when(pl.col("market_key") == m).then(pl.col(stat)) for m, (stat, _) in MARKETS.items()]
    )
    return both.with_columns(actual=actual.cast(pl.Float64))


def with_raw_mean(lines: pl.DataFrame) -> pl.DataFrame:
    """Unscaled mean: L + z * sigma needs sigma, so keep z; receptions get Poisson lambda."""
    lam = [
        poisson_lambda(line, p) if m == "player_receptions" else np.nan
        for m, line, p in lines.select("market_key", "line", "p_over").iter_rows()
    ]
    return lines.with_columns(
        z=pl.Series(norm.ppf(lines["p_over"].to_numpy())).clip(-Z_CLAMP, Z_CLAMP),
        lam=pl.Series(lam),
    )


def fit_market(rows: pl.DataFrame, market: str) -> tuple[float, float]:
    """(r_m, sigma_m) from rows with actuals."""
    if market == "player_receptions":
        return float(rows["actual"].sum() / rows["lam"].sum()), 0.0
    sigma = float((rows["actual"] - rows["line"]).std())
    return float(rows["actual"].sum() / (rows["line"] + rows["z"] * sigma).sum()), sigma


def prop_means(test: pl.DataFrame, fit2023: pl.DataFrame) -> tuple[pl.DataFrame, list[dict]]:
    """Prop mean per test line; parameters per market and week, fit on earlier data only."""
    fixed = {m: fit_market(fit2023.filter(pl.col("market_key") == m), m) for m in FIT_ON_2023}
    out, params = [], []
    for (market, week), g in test.group_by("market_key", "week"):
        if market in fixed:
            r, sigma = fixed[market]
        else:
            earlier = test.filter((pl.col("market_key") == market) & (pl.col("week") < week))
            if earlier.is_empty():
                continue
            r, sigma = fit_market(earlier, market)
        params.append({"market": market, "week": week, "r": r, "sigma": sigma})
        base = pl.col("lam") if market == "player_receptions" else pl.col("line") + pl.col("z") * sigma
        out.append(g.with_columns(prop_mean=r * base))
    return pl.concat(out), params


def lagged_means(stats: pl.DataFrame, points: pl.DataFrame, weights: dict[str, dict[str, float]]) -> pl.DataFrame:
    """Per league and player game: mean over his previous LAG_GAMES games of each line stat and
    of the remaining points (league points minus the four line stats' points)."""
    s = stats.select(pl.col("player_id").alias("gsis_id"), "season", "week", *[st for st, _ in MARKETS.values()])
    parts = []
    for lid, w in weights.items():
        line_pts = sum(pl.col(st).fill_null(0) * w.get(key, 0.0) for st, key in MARKETS.values())
        g = (
            points.filter(pl.col("league_id") == lid)
            .select(*KEYS, "points")
            .join(s, on=["gsis_id", "season", "week"], how="left")
            .with_columns(rest=pl.col("points") - line_pts)
            .sort("gsis_id", "season", "week")
        )
        lagged = [
            pl.col(c).fill_null(0).shift(1).rolling_mean(LAG_GAMES, min_samples=1).over("gsis_id").alias(f"lag_{c}")
            for c in [*[st for st, _ in MARKETS.values()], "rest"]
        ]
        parts.append(g.select(*KEYS, *lagged))
    return pl.concat(parts)


def clustered_ols(y: np.ndarray, x: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """OLS of y on [1, x] with CR1 cluster-robust standard errors: (beta, t)."""
    a = np.column_stack([np.ones(len(y)), x])
    bread = np.linalg.inv(a.T @ a)
    beta = bread @ a.T @ y
    u = y - a @ beta
    meat = np.zeros((a.shape[1], a.shape[1]))
    for g in np.unique(groups):
        s = a[groups == g].T @ u[groups == g]
        meat += np.outer(s, s)
    n, k, n_g = len(y), a.shape[1], len(np.unique(groups))
    v = bread @ meat @ bread * n_g / (n_g - 1) * (n - 1) / (n - k)
    return beta, beta / np.sqrt(np.diag(v))


def covered_rows(means: pl.DataFrame, protocol: pl.DataFrame, lags: pl.DataFrame, weights: dict[str, dict[str, float]]) -> pl.DataFrame:
    wide = means.group_by("gsis_id", "season", "week").agg(
        pl.col("game_id").first(),
        *[pl.col("prop_mean").filter(pl.col("market_key") == m).first().alias(m) for m in MARKETS],
    )
    rows = protocol.join(wide, on=["gsis_id", "season", "week"]).join(lags, on=KEYS, how="left")
    cover = pl.lit(False)
    for pos, markets in PRIMARY.items():
        cover = cover | ((pl.col("position") == pos) & pl.all_horizontal([pl.col(m).is_not_null() for m in markets]))
    rows = rows.filter(cover)
    parts = []
    for lid, w in weights.items():
        x = sum(
            pl.coalesce(pl.col(m), pl.col(f"lag_{st}")).fill_null(0) * w.get(key, 0.0)
            for m, (st, key) in MARKETS.items()
        )
        x_lag = sum(pl.col(f"lag_{st}").fill_null(0) * w.get(key, 0.0) for st, key in MARKETS.values())
        parts.append(
            rows.filter(pl.col("league_id") == lid).with_columns(x=x, x_lag=x_lag).with_columns(
                f=pl.col("x") + pl.col("lag_rest").fill_null(0),
                f_lag=pl.col("x_lag") + pl.col("lag_rest").fill_null(0),  # control: no lines
            )
        )
    return pl.concat(parts)


def score(rows: pl.DataFrame, names: dict[str, str]) -> None:
    for (lid,), g in rows.group_by("league_id"):
        y = g["points"].to_numpy()
        beta, t = clustered_ols(y, g.select("learned", "x").to_numpy(), g["game_id"].to_numpy())
        g = g.with_columns(blend=0.5 * pl.col("learned") + 0.5 * pl.col("f"))
        rmse = {c: float(np.sqrt(((y - g[c].to_numpy()) ** 2).mean())) for c in ("learned", "f", "blend")}
        wk = g.group_by("week").agg(
            ((pl.col("points") - pl.col("learned")) ** 2 - (pl.col("points") - pl.col("blend")) ** 2).mean().alias("d")
        )["d"].to_numpy()
        t_wk = float(wk.mean() / (wk.std(ddof=1) / np.sqrt(len(wk))))
        gain = 100 * (rmse["learned"] - rmse["blend"]) / rmse["learned"]
        ok = abs(t[2]) >= MIN_T and gain > 0 and abs(t_wk) >= MIN_T
        print(
            f"{names[lid]:9} n {g.height} games {g['game_id'].n_unique()} weeks {len(wk)} | "
            f"b_learned {beta[1]:.3f} (t {t[1]:.1f}) b_X {beta[2]:.3f} (t {t[2]:.1f}) | RMSE learned "
            f"{rmse['learned']:.4f} F {rmse['f']:.4f} blend {rmse['blend']:.4f} gain {gain:+.2f}% "
            f"weekly t {t_wk:.2f} weeks better {(wk > 0).sum()}/{len(wk)} | pass {ok}"
        )
        by_pos = g.group_by("position").agg(
            pl.len().alias("n"),
            ((pl.col("points") - pl.col("learned")) ** 2).mean().sqrt().alias("rmse_learned"),
            ((pl.col("points") - pl.col("blend")) ** 2).mean().sqrt().alias("rmse_blend"),
        ).sort("position")
        print(by_pos)
        control(g, names[lid])


def control(g: pl.DataFrame, name: str) -> None:
    """Not part of the rule: is the gain the lines, or just averaging with lagged means? Swap the
    prop means for the player's lagged means (F_lag), and add X_lag to the regression."""
    y = g["points"].to_numpy()
    _, t = clustered_ols(y, g.select("learned", "x", "x_lag").to_numpy(), g["game_id"].to_numpy())
    g = g.with_columns(blend_lag=0.5 * pl.col("learned") + 0.5 * pl.col("f_lag"))
    rmse = float(np.sqrt(((y - g["blend_lag"].to_numpy()) ** 2).mean()))
    wk = g.group_by("week").agg(
        ((pl.col("points") - pl.col("blend_lag")) ** 2 - (pl.col("points") - pl.col("blend")) ** 2).mean().alias("d")
    )["d"].to_numpy()
    bias = {c: float((g[c] - g["points"]).mean()) for c in ("learned", "f", "blend")}
    print(
        f"  control {name}: t on X with X_lag added {t[2]:.1f} (X_lag t {t[3]:.1f}); blend with F_lag RMSE "
        f"{rmse:.4f}; prop blend vs lag blend weekly t {wk.mean() / (wk.std(ddof=1) / np.sqrt(len(wk))):.2f}; "
        f"mean error learned {bias['learned']:+.2f} F {bias['f']:+.2f} blend {bias['blend']:+.2f}"
    )


def coverage(protocol: pl.DataFrame, means: pl.DataFrame, rows: pl.DataFrame) -> None:
    lid = protocol["league_id"].min()
    p = protocol.filter(pl.col("league_id") == lid)
    has_any = p.join(means.select("gsis_id", "season", "week").unique(), on=["gsis_id", "season", "week"], how="semi")
    cov = rows.filter(pl.col("league_id") == lid)
    print(f"protocol rows {TEST_SEASON} weeks {FIRST_WEEK}-17: {p.height}; any line {has_any.height}; covered {cov.height}")
    ranked = p.with_columns(rank=pl.col("learned").rank("ordinal", descending=True).over("week"))
    hit =ranked.with_columns(covered=pl.struct("gsis_id", "week").is_in(cov.select(pl.struct("gsis_id", "week")).to_series().implode()))
    for top in (24, 48, 96, 150):
        share = hit.filter(pl.col("rank") <= top).group_by("week").agg(pl.col("covered").mean())["covered"].mean()
        print(f"  top {top} by learned projection per week: {100 * share:.0f}% covered")
    print(p.join(cov.select("gsis_id", "week"), on=["gsis_id", "week"], how="semi").group_by("position").len().sort("position").join(p.group_by("position").len().rename({"len": "all"}), on="position"))


def main() -> None:
    self_check()
    archive = Path(sys.argv[1]) if len(sys.argv) > 1 else ARCHIVE
    schedule = store.read_table("nfl_schedules", "raw")
    stats = store.read_table("nfl_player_stats", "raw")
    points = store.read_table("player_points")
    leagues = store.read_table("leagues", "raw")
    weights = {
        r["league_id"]: json.loads(s) if isinstance(s := r["scoring_settings"], str) else s
        for r in leagues.iter_rows(named=True)
    }
    names = bias_check.league_names()
    abbr = team_abbr(archive)

    test = load_lines(archive / TEST_FILE, abbr, schedule).filter(pl.col("season") == TEST_SEASON)
    fit = pl.concat([load_lines(archive / f, abbr, schedule) for f in FIT_FILES], how="diagonal_relaxed")
    fit = fit.filter(pl.col("season") == FIT_SEASON)
    print(f"test lines {test.height} (games {test['game_id'].n_unique()}, lead minutes median {test['lead_min'].median()}, "
          f"books {test['bookmaker_key'].unique().to_list()}); fit lines {fit.height} (lead median {fit['lead_min'].median()})")
    test_m = with_raw_mean(match_players(test, stats))
    fit_m = with_raw_mean(match_players(fit, stats))
    print(f"matched to a stat row: test {test_m.height}/{test.height}, fit {fit_m.height}/{fit.height}")
    means, params = prop_means(test_m, fit_m)
    p = pl.DataFrame(params)
    print(p.group_by("market").agg(pl.col("r").last(), pl.col("sigma").last(), pl.col("r").min().alias("r_min"), pl.col("r").max().alias("r_max")).sort("market"))

    protocol = bias_check.protocol_rows().filter(
        pl.col("protocol") & (pl.col("season") == TEST_SEASON) & pl.col("week").is_between(FIRST_WEEK, 17)
    )
    lags = lagged_means(stats, points, weights)
    rows = covered_rows(means.filter(pl.col("week") >= FIRST_WEEK), protocol, lags, weights)
    coverage(protocol, means, rows)
    score(rows, names)


if __name__ == "__main__":
    main()
