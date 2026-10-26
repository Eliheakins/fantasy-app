"""Sleeper blend weight by position on clean pre-kickoff snapshots (issue #40).

Per player-game: the last snapshot fetched before that team's kickoff of ours (`proj_snapshots`,
learned) and of Sleeper's (`sleeper_proj_snapshots`, scored under each league's rules), through
the scorecard's own helpers, so the rows are the scorecard's rows.

1. Per league and position: RMSE of learned alone, Sleeper alone and the production 0.5 blend.
2. A non-negative least-squares fit of points on [learned, Sleeper] (no intercept), leave one week
   out: each week is predicted by weights fit on the other weeks. RMSE at 0.5 and at the fitted
   weights, paired t over held-out weeks on the per-week squared-error difference. Keep 0.5 unless
   the fitted weights are better with |t| >= 2. The week-level t overstates evidence (players in a
   week share game scripts), so read 2 as about 1.5.
3. The rule that a Sleeper 0 counts as missing for Questionable and Doubtful players (decisions,
   2026-10-23) against blending the 0. Both go through the chance of playing: value = p * learned
   (rule) against p * (0.5 * learned + 0.5 * 0) (blend), scored against points, 0 for a player
   with no stat line in a final game. p is the `availability` table's p_play where it has the
   week, else the historical share of report-listed regulars with that status who had a stat line.

Rows where production would not blend (Sleeper missing, or a Questionable or Doubtful Sleeper 0)
are left out of the weight fit. Injury status is the nflverse game-week report, a stand-in for the
Sleeper status that production reads.

Run from the repo root: uv run python research/blend_weight.py
"""

import numpy as np
import polars as pl
from scipy.optimize import nnls

from fantasy import store
from fantasy._scorecard import KEY, _kickoff_frame, _last_before_kickoff, _sleeper_points, score_games
from fantasy.sim.blend import SLEEPER_WEIGHT
from fantasy.stages.simulate import SLEEPER_ZEROED_STATUSES

MIN_T = 2.0
MIN_WEEKS = 3  # a paired t needs at least this many held-out weeks
STATUS_FIT_SEASONS = (2021, 2025)
pl.Config(tbl_rows=40, tbl_cols=14, tbl_width_chars=180, float_precision=3)


# ---------- the method (pure, checked on synthetic data below) ----------


def fit_weights(learned: np.ndarray, sleeper: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    coef, _ = nnls(np.column_stack([learned, sleeper]), y)
    return float(coef[0]), float(coef[1])


def leave_one_week_out(rows: pl.DataFrame) -> pl.DataFrame:
    """rows: week, learned, sleeper, actual. Adds `fitted` (weights fit on the other weeks) and
    `w_sleeper` (the implied Sleeper share b / (a + b) of that fit). Empty with one week."""
    weeks = sorted(rows["week"].unique().to_list())
    if len(weeks) < 2:
        return rows.clear().with_columns(fitted=pl.lit(0.0), w_sleeper=pl.lit(0.0))
    parts = []
    for week in weeks:
        train, test = rows.filter(pl.col("week") != week), rows.filter(pl.col("week") == week)
        a, b = fit_weights(
            train["learned"].to_numpy(), train["sleeper"].to_numpy(), train["actual"].to_numpy()
        )
        parts.append(
            test.with_columns(
                fitted=a * pl.col("learned") + b * pl.col("sleeper"),
                w_sleeper=pl.lit(b / (a + b) if a + b > 0 else float("nan")),
            )
        )
    return pl.concat(parts)


def compare(held: pl.DataFrame) -> dict[str, float | int | str]:
    """Held-out rows with `fitted`: RMSE at 0.5 and fitted, paired t over weeks, the verdict."""
    d = held.with_columns(
        half=(1 - SLEEPER_WEIGHT) * pl.col("learned") + SLEEPER_WEIGHT * pl.col("sleeper")
    )
    by_week = d.group_by("week").agg(
        ((pl.col("half") - pl.col("actual")) ** 2).mean().alias("se_half"),
        ((pl.col("fitted") - pl.col("actual")) ** 2).mean().alias("se_fit"),
    )
    diff = (by_week["se_half"] - by_week["se_fit"]).to_numpy()
    enough = len(diff) >= MIN_WEEKS and diff.std(ddof=1) > 0
    t = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))) if enough else float("nan")
    rmse_half = float(((d["half"] - d["actual"]) ** 2).mean() ** 0.5)
    rmse_fit = float(((d["fitted"] - d["actual"]) ** 2).mean() ** 0.5)
    adopt = enough and abs(t) >= MIN_T and rmse_fit < rmse_half
    return {
        "n": d.height,
        "weeks": len(diff),
        "rmse_0.5": round(rmse_half, 3),
        "rmse_fit": round(rmse_fit, 3),
        "w_sleeper_mean": round(float(d["w_sleeper"].mean()), 3),
        "t": round(t, 2),
        "weeks_better": f"{int((diff > 0).sum())}/{len(diff)}",
        "verdict": "fitted" if adopt else f"keep {SLEEPER_WEIGHT}",
    }


def self_check() -> None:
    """A known weight is recovered and adopted; with no signal 0.5 is kept."""
    rng = np.random.default_rng(0)
    n_weeks, per_week = 6, 400
    truth = rng.gamma(2.0, 4.0, n_weeks * per_week)
    learned = truth + rng.normal(0, 2.0, truth.size)
    sleeper = truth + rng.normal(0, 2.0, truth.size)
    week = np.repeat(np.arange(1, n_weeks + 1), per_week)
    y = 0.15 * learned + 0.85 * sleeper + rng.normal(0, 1.0, truth.size)
    rows = pl.DataFrame({"week": week, "learned": learned, "sleeper": sleeper, "actual": y})
    a, b = fit_weights(learned, sleeper, y)
    assert abs(b / (a + b) - 0.85) < 0.02, (a, b)
    result = compare(leave_one_week_out(rows))
    assert result["verdict"] == "fitted" and float(result["t"]) >= MIN_T, result
    assert abs(float(result["w_sleeper_mean"]) - 0.85) < 0.02, result
    # equal information: the fitted weight should sit near 0.5 and not be adopted
    y_even = truth + rng.normal(0, 3.0, truth.size)
    even = rows.with_columns(actual=pl.Series(y_even))
    result_even = compare(leave_one_week_out(even))
    assert abs(float(result_even["w_sleeper_mean"]) - 0.5) < 0.05, result_even
    assert result_even["verdict"] == f"keep {SLEEPER_WEIGHT}", result_even
    # one week: nothing to hold out
    assert leave_one_week_out(rows.filter(pl.col("week") == 1)).is_empty()
    print("self-check passed: weight 0.85 recovered and adopted; 0.5 kept with no signal")


# ---------- data ----------


def league_rows(league: dict) -> tuple[pl.DataFrame, dict[str, int], pl.DataFrame]:
    """Scored rows (KEY, team, position, actual, learned, baseline, sleeper, status), the
    scorecard's exclusion counts, and the Q/D Sleeper-0 rows of final games (actual 0 when the
    player has no stat line)."""
    lid = league["league_id"]
    snaps = store.read_table("proj_snapshots", "archive").filter(pl.col("league_id") == lid)
    meta = store.read_table("proj_baseline").filter(pl.col("league_id") == lid)
    games = snaps.select(*KEY).unique().join(meta.select(*KEY, "team", "position"), on=KEY, how="left")
    points = store.read_table("player_points").filter(pl.col("league_id") == lid).select(*KEY, "points")
    kick = _kickoff_frame(games, store.read_table("nfl_schedules", "raw"))
    id_map = store.read_table("id_map").select("sleeper_id", "gsis_id")
    sleeper = _sleeper_points(store.read_table("sleeper_proj_snapshots", "archive"), league, id_map, games)
    scored, excluded = score_games(games, snaps, sleeper, points, kick)
    status = (
        store.read_table("nfl_injuries", "raw")
        .filter(pl.col("game_type") == "REG")
        .select("gsis_id", "season", "week", pl.col("report_status").alias("status"))
        .unique(["gsis_id", "season", "week"], keep="first")
    )
    scored = scored.join(status, on=["gsis_id", "season", "week"], how="left")
    # Q/D with a Sleeper 0, in games that are final (the team's game has a score)
    final = (
        store.read_table("team_games")
        .filter(pl.col("points_for").is_not_null())
        .select("season", "week", "team")
    )
    window = games.join(final, on=["season", "week", "team"], how="semi").join(
        kick, on=["season", "week", "team"]
    )
    ours = _last_before_kickoff(snaps, window.select(*KEY, "kickoff")).select(*KEY, "learned")
    theirs = _last_before_kickoff(sleeper, window.select(*KEY, "kickoff")).select(*KEY, "sleeper")
    zeroed = (
        window.select(*KEY, "position")
        .join(ours, on=KEY)
        .join(theirs, on=KEY)
        .join(status, on=["gsis_id", "season", "week"])
        .filter(pl.col("status").is_in(list(SLEEPER_ZEROED_STATUSES)) & (pl.col("sleeper") == 0))
        .join(points, on=KEY, how="left")
        .with_columns(pl.col("points").fill_null(0.0).alias("actual"))
    )
    return scored, excluded, zeroed


def status_play_rates(league_id: str) -> dict[str, float]:
    """Share of report-listed regulars (a stat line in one of the two prior weeks) with a stat
    line in the game, by status, seasons STATUS_FIT_SEASONS."""
    lo, hi = STATUS_FIT_SEASONS
    pts = store.read_table("player_points").filter(pl.col("league_id") == league_id)
    have = pts.select("gsis_id", "season", "week").with_columns(pl.lit(True).alias("statline"))
    prior = pl.concat(
        [have.with_columns(pl.col("week") + k).select("gsis_id", "season", "week") for k in (1, 2)]
    ).unique()
    inj = (
        store.read_table("nfl_injuries", "raw")
        .filter(
            (pl.col("game_type") == "REG")
            & pl.col("season").is_between(lo, hi)
            & pl.col("report_status").is_in(list(SLEEPER_ZEROED_STATUSES))
        )
        .unique(["gsis_id", "season", "week"], keep="first")
        .join(prior, on=["gsis_id", "season", "week"], how="semi")
        .join(have, on=["gsis_id", "season", "week"], how="left")
        .with_columns(pl.col("statline").fill_null(False))
    )
    rates = inj.group_by("report_status").agg(pl.col("statline").mean())
    return dict(zip(rates["report_status"], rates["statline"], strict=True))


def score_zero_rule(zeroed: pl.DataFrame, rates: dict[str, float]) -> dict[str, float | int]:
    if zeroed.is_empty():
        return {"n": 0}
    avail = store.read_table("availability").select("gsis_id", "season", "week", "p_play")
    d = zeroed.join(avail, on=["gsis_id", "season", "week"], how="left").with_columns(
        p=pl.coalesce("p_play", pl.col("status").replace_strict(rates, default=None))
    )
    rule = pl.col("p") * pl.col("learned")
    mixed = pl.col("p") * (1 - SLEEPER_WEIGHT) * pl.col("learned")
    out = d.select(
        pl.len().alias("n"),
        ((rule - pl.col("actual")) ** 2).mean().sqrt().alias("rmse_rule"),
        ((mixed - pl.col("actual")) ** 2).mean().sqrt().alias("rmse_blend0"),
        (rule - pl.col("actual")).mean().alias("me_rule"),
        (mixed - pl.col("actual")).mean().alias("me_blend0"),
        pl.col("p_play").is_not_null().sum().alias("n_with_p_play"),
    )
    return {k: (round(v, 3) if isinstance(v, float) else v) for k, v in out.row(0, named=True).items()}


def main() -> None:
    self_check()
    for league in store.read_table("leagues", "raw").iter_rows(named=True):
        name = league["name"].split()[0]
        scored, excluded, zeroed = league_rows(league)
        print(f"\n=== {name}: scorecard exclusions {excluded}")
        blendable = scored.filter(
            pl.col("learned").is_not_null()
            & pl.col("sleeper").is_not_null()
            & ~(pl.col("status").is_in(list(SLEEPER_ZEROED_STATUSES)) & (pl.col("sleeper") == 0))
        )
        print(f"rows with both projections (production blends them): {blendable.height}, "
              f"weeks {sorted(blendable['week'].unique().to_list())}")
        if blendable.height:
            half = (1 - SLEEPER_WEIGHT) * pl.col("learned") + SLEEPER_WEIGHT * pl.col("sleeper")
            print(
                blendable.group_by("position")
                .agg(
                    pl.len().alias("n"),
                    ((pl.col("learned") - pl.col("actual")) ** 2).mean().sqrt().alias("rmse_learned"),
                    ((pl.col("sleeper") - pl.col("actual")) ** 2).mean().sqrt().alias("rmse_sleeper"),
                    ((half - pl.col("actual")) ** 2).mean().sqrt().alias("rmse_0.5"),
                    (pl.col("learned") - pl.col("actual")).mean().alias("me_learned"),
                    (pl.col("sleeper") - pl.col("actual")).mean().alias("me_sleeper"),
                )
                .sort("position")
            )
        results = []
        for pos in [*sorted(blendable["position"].drop_nulls().unique().to_list()), "ALL"]:
            rows = blendable if pos == "ALL" else blendable.filter(pl.col("position") == pos)
            held = leave_one_week_out(rows.select("week", "learned", "sleeper", "actual"))
            results.append(
                {"position": pos, **compare(held)}
                if held.height
                else {"position": pos, "n": rows.height, "verdict": "untestable: fewer than 2 weeks"}
            )
        print(pl.DataFrame(results))
        rates = status_play_rates(league["league_id"])
        print(f"Q/D Sleeper-0 rule (status play rates {({k: round(v, 3) for k, v in rates.items()})}):",
              score_zero_rule(zeroed, rates))


if __name__ == "__main__":
    main()
