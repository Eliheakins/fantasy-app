"""Anytime-touchdown prices against Sleeper and our lagged expected touchdowns (live weeks).

Reads every archived Odds API snapshot under data/archive/odds/<stamp>/ (`make odds`), keeps for
each game, book and player the last price taken before kickoff, and scores three forecasts of
P(player scores a rushing, receiving or return touchdown) on finished games:
  market    the books only quote "Yes", so there is no two-way price to de-vig. Per game, team and
            book the implied probabilities q are mapped to p = q ** k (power method), k set so the
            team's expected touchdowns sum(-ln(1 - p)) equals a + b * implied team total (a, b fit
            on 2019 to 2025 regular-season games). Check: p = s * q with s set the same way.
            Books are then averaged per player.
  sleeper   1 - exp(-(rush_td + rec_td)) from the last Sleeper snapshot fetched before kickoff
            (data/archive/sleeper_proj_snapshots.parquet).
  ours      1 - exp(-lambda), lambda the player's expected touchdowns (nflverse ff_opportunity,
            rush plus receiving) averaged with half-life 4 games over games before this one, as
            the learned model lags them.
Rows: players with all three forecasts who were active (a stat or snap row), in games with a
final score. Brier and log loss, paired per player; t of the mean difference with standard
errors clustered by game. A forecast is better when |t| >= 2.

Run from the repo root: OMP_NUM_THREADS=3 uv run python research/props_td_check.py [--self-check]
"""

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl
from scipy.optimize import brentq

from fantasy import store

ODDS_DIR = store.DATA_DIR / "archive" / "odds"
SLEEPER_SNAPSHOTS = store.DATA_DIR / "archive" / "sleeper_proj_snapshots.parquet"
MARKET = "player_anytime_td"
FIT_SEASONS = range(2019, 2026)
HALF_LIFE = 4.0
P_MAX = 0.99  # a price above this is treated as this
EPS = 1e-6
MIN_T = 2.0
SKILL = ("QB", "RB", "WR", "TE")
SLEEPER_TEAM = {"LAR": "LA"}  # Sleeper abbreviation -> nflverse
SUFFIX = r"\b(jr|sr|ii|iii|iv|v)\b"
TEAMS = {
    "Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL",
    "Buffalo Bills": "BUF", "Carolina Panthers": "CAR", "Chicago Bears": "CHI",
    "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL",
    "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
    "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
    "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC",
    "Los Angeles Rams": "LA", "Miami Dolphins": "MIA", "Minnesota Vikings": "MIN",
    "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
    "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT",
    "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB",
    "Tennessee Titans": "TEN", "Washington Commanders": "WAS",
}


def norm_name(name: pl.Expr) -> pl.Expr:
    lowered = name.str.to_lowercase().str.replace_all(r"[.'\-]", "")
    return lowered.str.replace_all(SUFFIX, "").str.replace_all(r"\s+", " ").str.strip_chars()


def implied(price: pl.Expr) -> pl.Expr:
    q = pl.when(price < 0).then(-price / (-price + 100)).otherwise(100 / (price + 100))
    return q.clip(EPS, P_MAX)


def load_prices(odds_dir: Path) -> pl.DataFrame:
    """One row per game, book and player: the last 'Yes' price archived before kickoff."""
    rows = []
    for snap in sorted(p for p in odds_dir.iterdir() if p.is_dir() and not p.suffix):
        taken = datetime.strptime(snap.name, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        for path in snap.glob("*.json"):
            event = json.loads(path.read_text())
            for book in event.get("bookmakers", []):
                for market in book.get("markets", []):
                    if market["key"] != MARKET:
                        continue
                    rows += [
                        {
                            "event_id": event["id"], "kick": event["commence_time"],
                            "home": TEAMS.get(event["home_team"]), "away": TEAMS.get(event["away_team"]),
                            "book": book["key"], "player": o["description"], "price": float(o["price"]),
                            "taken": taken,
                        }
                        for o in market["outcomes"]
                        if o.get("name") == "Yes" and o.get("description")
                    ]
    if not rows:
        return pl.DataFrame()
    d = pl.DataFrame(rows).with_columns(
        kick=pl.col("kick").str.to_datetime(time_zone="UTC"), name=norm_name(pl.col("player"))
    )
    return (
        d.filter(pl.col("taken") < pl.col("kick"))
        .sort("taken")
        .group_by("event_id", "book", "name")
        .last()
        .with_columns(q=implied(pl.col("price")))
    )


def match_players(prices: pl.DataFrame, players: pl.DataFrame, id_map: pl.DataFrame) -> pl.DataFrame:
    """Team by name within the game's two teams (Sleeper's player file, any position, so the
    team's whole list enters the de-vig); gsis_id from id_map where it exists."""
    p = players.filter(pl.col("team").is_not_null()).select(
        "sleeper_id", "position",
        pl.col("team").replace(SLEEPER_TEAM).alias("team"),
        norm_name(pl.col("full_name")).alias("name"),
    )
    ids = id_map.select("sleeper_id", pl.col("gsis_id").str.strip_chars()).drop_nulls().unique("sleeper_id")
    out = prices.join(p, on="name").filter((pl.col("team") == pl.col("home")) | (pl.col("team") == pl.col("away")))
    out = out.unique(["event_id", "book", "name"], keep="none")  # drop names two players share
    return out.join(ids, on="sleeper_id", how="left")


def team_td_fit(stats: pl.DataFrame, schedule: pl.DataFrame) -> tuple[float, float]:
    """(a, b) in rush + receiving + return TDs per team-game = a + b * implied team total."""
    tds = (
        stats.filter((pl.col("season_type") == "REG") & pl.col("season").is_in(list(FIT_SEASONS)))
        .group_by("season", "week", "team")
        .agg((pl.col("rushing_tds") + pl.col("receiving_tds") + pl.col("special_teams_tds")).fill_null(0).sum().alias("tds"))
    )
    implied_totals = team_totals(schedule)
    d = tds.join(implied_totals, on=["season", "week", "team"]).drop_nulls("implied")
    b, a = np.polyfit(d["implied"].to_numpy(), d["tds"].to_numpy(), 1)
    return float(a), float(b)


def team_totals(schedule: pl.DataFrame) -> pl.DataFrame:
    """Implied points per team-game; nflverse spread_line is positive when home is favored."""
    s = schedule.select("game_id", "season", "week", "gameday", "home_team", "away_team", "home_score", "spread_line", "total_line")
    home = (pl.col("total_line") + pl.col("spread_line")) / 2
    away = (pl.col("total_line") - pl.col("spread_line")) / 2
    return pl.concat(
        [
            s.select("game_id", "season", "week", "gameday", "home_score", pl.col("home_team").alias("team"), home.alias("implied")),
            s.select("game_id", "season", "week", "gameday", "home_score", pl.col("away_team").alias("team"), away.alias("implied")),
        ]
    )


def solve_scale(q: np.ndarray, target: float, power: bool) -> np.ndarray:
    """p = q ** k (power) or s * q (multiplicative) with sum(-ln(1 - p)) = target."""
    def expected(x: float) -> float:
        p = np.minimum(q**x if power else q * x, P_MAX)
        return float(-np.log1p(-p).sum()) - target

    lo, hi = (0.05, 20.0) if power else (1e-3, 1.0 / q.max())
    if expected(lo) * expected(hi) > 0:  # cannot reach the target: leave the prices as they are
        return q
    x = brentq(expected, lo, hi)
    return np.minimum(q**x if power else q * x, P_MAX)


def devig(matched: pl.DataFrame, fit: tuple[float, float]) -> pl.DataFrame:
    """Per player: market probability averaged over books, by the power and the multiplicative
    method. `matched` needs event_id, book, team, gsis_id, q and implied."""
    a, b = fit
    parts = []
    for _, g in matched.group_by("event_id", "team", "book"):
        target = a + b * g["implied"][0]
        q = g["q"].to_numpy()
        parts.append(g.with_columns(p_power=pl.Series(solve_scale(q, target, True)), p_mult=pl.Series(solve_scale(q, target, False))))
    return pl.concat(parts).group_by("event_id", "gsis_id", "sleeper_id", "team", "season", "week", "game_id", "kick").agg(
        pl.col("p_power").mean(), pl.col("p_mult").mean(), pl.col("book").n_unique().alias("books")
    )


def sleeper_probs(snapshots: pl.DataFrame, rows: pl.DataFrame) -> pl.DataFrame:
    """Last Sleeper snapshot fetched before each row's kickoff."""
    s = snapshots.with_columns(fetched=pl.col("fetched_at").str.to_datetime(time_zone="UTC")).with_columns(
        lam=pl.col("stats").str.json_path_match("$.rush_td").cast(pl.Float64).fill_null(0)
        + pl.col("stats").str.json_path_match("$.rec_td").cast(pl.Float64).fill_null(0)
    )
    j = rows.select("event_id", "sleeper_id", "week", "kick").join(s.select("sleeper_id", "week", "fetched", "lam"), on=["sleeper_id", "week"])
    last = j.filter(pl.col("fetched") < pl.col("kick")).sort("fetched").group_by("event_id", "sleeper_id").last()
    return last.select("event_id", "sleeper_id", p_sleeper=1 - (-pl.col("lam")).exp())


def ours_probs(opp: pl.DataFrame, rows: pl.DataFrame) -> pl.DataFrame:
    """Expected TDs averaged (half-life 4 games) over each player's games before the target."""
    g = (
        opp.select(
            pl.col("player_id").alias("gsis_id"), "season", "week",
            (pl.col("rush_touchdown_exp").cast(pl.Float64).fill_null(0) + pl.col("rec_touchdown_exp").cast(pl.Float64).fill_null(0)).alias("td"),
        )
        .unique(["gsis_id", "season", "week"])
        .sort("gsis_id", "season", "week")
        .with_columns(lam=pl.col("td").ewm_mean(half_life=HALF_LIFE).over("gsis_id"), t=store.week_index())
    )
    target = rows.select("event_id", "gsis_id", "season", "week").with_columns(t=store.week_index()).sort("t")
    j = target.join_asof(g.select("gsis_id", "t", "lam").sort("t"), on="t", by="gsis_id", strategy="backward", allow_exact_matches=False, check_sortedness=False)
    return j.select("event_id", "gsis_id", p_ours=1 - (-pl.col("lam")).exp())


def outcomes(stats: pl.DataFrame, snaps: pl.DataFrame) -> pl.DataFrame:
    """Active players per game and whether they scored a non-passing touchdown."""
    tds = stats.select(
        pl.col("player_id").alias("gsis_id"), "season", "week",
        (pl.col("rushing_tds") + pl.col("receiving_tds") + pl.col("special_teams_tds")).fill_null(0).alias("tds"),
    )
    active = snaps.filter((pl.col("offense_snaps") > 0) | (pl.col("st_snaps") > 0)).select("gsis_id", "season", "week")
    base = pl.concat([tds.select("gsis_id", "season", "week"), active]).unique()
    return base.join(tds, on=["gsis_id", "season", "week"], how="left").select(
        "gsis_id", "season", "week", scored=(pl.col("tds").fill_null(0) > 0).cast(pl.Float64)
    )


def clustered_mean_t(d: np.ndarray, groups: np.ndarray) -> float:
    """t of mean(d) with CR1 standard errors clustered by group."""
    u = d - d.mean()
    ids = np.unique(groups)
    sums = np.array([u[groups == g].sum() for g in ids])
    n_g = len(ids)
    if n_g < 2:
        return float("nan")
    se = np.sqrt((sums**2).sum() * n_g / (n_g - 1)) / len(d)
    return float(d.mean() / se)


def losses(p: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    p = np.clip(p, EPS, 1 - EPS)
    return (p - y) ** 2, -(y * np.log(p) + (1 - y) * np.log(1 - p))


def score(rows: pl.DataFrame) -> list[dict]:
    """Mean Brier and log loss per forecast; paired t for market against Sleeper and ours."""
    y = rows["scored"].to_numpy()
    games = rows["game_id"].to_numpy()
    loss = {c: losses(rows[c].to_numpy(), y) for c in ("p_power", "p_mult", "p_sleeper", "p_ours")}
    out = []
    for c, (brier, log) in loss.items():
        out.append({"forecast": c, "n": len(y), "brier": float(brier.mean()), "log_loss": float(log.mean())})
    for market in ("p_power", "p_mult"):
        for other in ("p_sleeper", "p_ours"):
            out.append(
                {
                    "forecast": f"{market} - {other}", "n": len(y),
                    "brier": float((loss[market][0] - loss[other][0]).mean()),
                    "log_loss": float((loss[market][1] - loss[other][1]).mean()),
                    "t_brier": clustered_mean_t(loss[market][0] - loss[other][0], games),
                    "t_log": clustered_mean_t(loss[market][1] - loss[other][1], games),
                }
            )
    return out


def self_check() -> None:
    """Synthetic league: power de-vig recovers true probabilities; the market made from them
    beats a noisy forecast with |t| >= 2; the clustered t of pure noise is small."""
    rng = np.random.default_rng(1)
    lam = rng.gamma(0.6, 0.3, size=12)
    p_true = 1 - np.exp(-lam)
    q = p_true ** (1 / 1.15)  # books shade toward the longshots
    p_hat = solve_scale(q, float(lam.sum()), True)
    assert np.max(np.abs(p_hat - p_true)) < 1e-6
    p_mult = solve_scale(q, float(lam.sum()), False)
    assert np.isclose(-np.log1p(-p_mult).sum(), lam.sum())

    n_games, per = 300, 12
    lam = rng.gamma(0.6, 0.3, size=n_games * per)
    p = 1 - np.exp(-lam)
    y = (rng.random(len(p)) < p).astype(float)
    noisy = np.clip(p * rng.lognormal(0, 0.6, len(p)), EPS, P_MAX)
    games = np.repeat(np.arange(n_games), per)
    rows = pl.DataFrame({"scored": y, "game_id": games, "p_power": p, "p_mult": p, "p_sleeper": noisy, "p_ours": noisy})
    res = {r["forecast"]: r for r in score(rows)}
    assert res["p_power - p_sleeper"]["t_log"] < -MIN_T and res["p_power - p_sleeper"]["brier"] < 0
    assert abs(clustered_mean_t(rng.normal(size=3000), np.repeat(np.arange(300), 10))) < 4
    print("self-check passed")


def main() -> None:
    self_check()
    if "--self-check" in sys.argv:
        return
    prices = load_prices(ODDS_DIR)
    if prices.is_empty():
        sys.exit(f"no anytime-TD prices under {ODDS_DIR}")
    schedule = store.read_table("nfl_schedules", "raw")
    stats = store.read_table("nfl_player_stats", "raw")
    fit = team_td_fit(stats, schedule)
    print(f"team TDs = {fit[0]:.3f} + {fit[1]:.4f} * implied total (2019-2025)")

    matched = match_players(prices, store.read_table("sleeper_players", "raw"), store.read_table("id_map"))
    games = team_totals(schedule).with_columns(gameday=pl.col("gameday").cast(pl.String))
    matched = matched.with_columns(
        gameday=pl.col("kick").dt.convert_time_zone("America/New_York").dt.strftime("%Y-%m-%d")
    ).join(games, on=["gameday", "team"])
    print(f"prices {prices.height} rows ({prices['event_id'].n_unique()} games, {prices['book'].n_unique()} books, "
          f"{prices['name'].n_unique()} names); matched {matched.height} rows, {matched['gsis_id'].n_unique()} players")
    unmatched = prices.join(matched, on=["event_id", "book", "name"], how="anti")
    print(f"unmatched names (left out of the de-vig): {unmatched['player'].unique().sort().to_list()}")
    market = devig(matched, fit).filter(pl.col("gsis_id").is_not_null())
    final = matched.filter(pl.col("home_score").is_not_null()).select("event_id").unique()
    rows = (
        market.join(sleeper_probs(pl.read_parquet(SLEEPER_SNAPSHOTS), market), on=["event_id", "sleeper_id"])
        .join(ours_probs(store.read_table("nfl_ff_opportunity", "raw"), market), on=["event_id", "gsis_id"])
        .drop_nulls(["p_sleeper", "p_ours"])
    )
    print(f"players with all three forecasts: {rows.height} in {rows['event_id'].n_unique()} games")
    scored = rows.join(final, on="event_id").join(
        outcomes(stats, store.read_table("nfl_snaps", "raw")), on=["gsis_id", "season", "week"]
    )
    print(f"scored (final game, player active): n {scored.height} in {scored['event_id'].n_unique()} games, "
          f"{int(scored['scored'].sum()) if scored.height else 0} scored")
    print(rows.select(pl.col("p_power", "p_mult", "p_sleeper", "p_ours").mean()))
    if scored["event_id"].n_unique() < 2:
        print("fewer than 2 finished games: nothing to score yet")
        return
    print(pl.DataFrame(score(scored)))


if __name__ == "__main__":
    main()
