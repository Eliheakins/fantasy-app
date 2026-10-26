"""Sleeper blend weight on clean pre-kickoff snapshots (issue #40).

Per player-game: our last snapshot fetched before that team's kickoff (`proj_snapshots`, learned,
passed through `distributions.calibrated` as `simulate` does before blending) and the Sleeper
snapshot (`sleeper_proj_snapshots`, scored under each league's rules) fetched before kickoff and
nearest in time to ours, so the pair is what one refresh would have blended. Actuals and
exclusions come from the scorecard's helpers.

1. Per league and position: RMSE of ours alone, Sleeper alone and the production 0.5 blend.
2. One weight w in [0, 1] on Sleeper, (1 - w) on ours (weights sum to 1, so a level error both
   sources share cannot be fit away), least squares, leave one week out: each week is predicted
   by w fit on the other weeks. RMSE at 0.5 and at the fitted w; paired t over held-out weeks on
   the per-week squared-error difference against the two-sided 5% t critical value for
   weeks - 1 degrees of freedom. Keep 0.5 unless the fitted w is better and clears it.
   Positions are pooled; a position gets its own verdict only with at least
   MIN_POSITION_WEEK_ROWS rows in every week. The two leagues score the same games, so their
   verdicts are not independent evidence, and players in a week share game scripts, so the
   week-level t still overstates.
3. The rule that a Sleeper 0 counts as missing for Questionable and Doubtful players (decisions,
   2026-10-23) against blending the 0. Both go through the chance of playing: value = p * ours
   (rule) against p * (0.5 * ours + 0.5 * 0) (blend), scored against points, 0 for a player
   with no stat line in a final game. p is the `availability` table's p_play where it has the
   week, else the historical share of report-listed regulars with that status who had a stat line.

4. Outside sources (`outside_proj_snapshots`, archived by the outside_projections stage), each
   mapped to gsis_id, scored under the league's rules plus the lagged fumble and two-point points
   (`prop_points.outside_points`), and prop-implied points rebuilt from the archived Odds API
   snapshots (each game's last snapshot before kickoff, `prop_points` functions, lags as of that
   week), paired like Sleeper (fetched before kickoff, nearest to ours). The shipped current-week
   blend, the equal-weight mean of every source a row has (ours, Sleeper, FFToday, props), is
   scored against the old 0.5 blend and against ours alone, on the same rows. Paired weekly t
   against the same critical value. Equal weights only: no weights are fit on so few weeks.

Rows where production would not blend (Sleeper missing, or a Questionable or Doubtful Sleeper 0)
are left out of the weight fit. Injury status is the nflverse game-week report, a stand-in for the
Sleeper status that production reads.

Run from the repo root: uv run python research/blend_weight.py
"""

import json

import numpy as np
import polars as pl
from scipy.stats import t as student_t

from fantasy import store
from fantasy._scorecard import KEY, _at, _kickoff_frame, _last_before_kickoff, _sleeper_points, score_games
from fantasy.sim.blend import SLEEPER_WEIGHT
from fantasy.config import load_config
from fantasy.stages import outside_projections as op
from fantasy.stages import prop_points as pp
from fantasy.stages.distributions import calibrated
from fantasy.stages.simulate import SLEEPER_ZEROED_STATUSES

ALPHA = 0.05
MIN_WEEKS = 3  # a paired t needs at least this many held-out weeks
MIN_POSITION_WEEK_ROWS = 100  # rows of a position in every week before it gets its own fit
STATUS_FIT_SEASONS = (2021, 2025)
pl.Config(tbl_rows=40, tbl_cols=14, tbl_width_chars=180, float_precision=3)


# ---------- the method (pure, checked on synthetic data below) ----------


def fit_weight(ours: np.ndarray, sleeper: np.ndarray, y: np.ndarray) -> float:
    """Least-squares w in [0, 1] for (1 - w) * ours + w * sleeper."""
    gap = sleeper - ours
    denom = float(gap @ gap)
    return float(np.clip(gap @ (y - ours) / denom, 0.0, 1.0)) if denom > 0 else SLEEPER_WEIGHT


def leave_one_week_out(rows: pl.DataFrame) -> pl.DataFrame:
    """rows: week, ours, sleeper, actual. Adds `fitted` and `w` (fit on the other weeks). Empty
    with fewer than two weeks."""
    weeks = sorted(rows["week"].unique().to_list())
    if len(weeks) < 2:
        return rows.clear().with_columns(fitted=pl.lit(0.0), w=pl.lit(0.0))
    parts = []
    for week in weeks:
        train, test = rows.filter(pl.col("week") != week), rows.filter(pl.col("week") == week)
        w = fit_weight(train["ours"].to_numpy(), train["sleeper"].to_numpy(), train["actual"].to_numpy())
        parts.append(
            test.with_columns(
                fitted=(1 - w) * pl.col("ours") + w * pl.col("sleeper"), w=pl.lit(w)
            )
        )
    return pl.concat(parts)


def compare(held: pl.DataFrame) -> dict[str, float | int | str]:
    """Held-out rows with `fitted`: RMSE at 0.5 and fitted, paired t over weeks, the verdict."""
    d = held.with_columns(
        half=(1 - SLEEPER_WEIGHT) * pl.col("ours") + SLEEPER_WEIGHT * pl.col("sleeper")
    )
    by_week = d.group_by("week").agg(
        ((pl.col("half") - pl.col("actual")) ** 2).mean().alias("se_half"),
        ((pl.col("fitted") - pl.col("actual")) ** 2).mean().alias("se_fit"),
    )
    diff = (by_week["se_half"] - by_week["se_fit"]).to_numpy()
    enough = len(diff) >= MIN_WEEKS and diff.std(ddof=1) > 0
    t = float(diff.mean() / (diff.std(ddof=1) / np.sqrt(len(diff)))) if enough else float("nan")
    critical = float(student_t.ppf(1 - ALPHA / 2, len(diff) - 1)) if len(diff) > 1 else float("nan")
    rmse_half = float(((d["half"] - d["actual"]) ** 2).mean() ** 0.5)
    rmse_fit = float(((d["fitted"] - d["actual"]) ** 2).mean() ** 0.5)
    adopt = enough and abs(t) >= critical and rmse_fit < rmse_half
    return {
        "n": d.height,
        "weeks": len(diff),
        "rmse_0.5": round(rmse_half, 3),
        "rmse_fit": round(rmse_fit, 3),
        "w_mean": round(float(d["w"].mean()), 3),
        "t": round(t, 2),
        "t_critical": round(critical, 2),
        "weeks_better": f"{int((diff > 0).sum())}/{len(diff)}",
        "verdict": "fitted" if adopt else f"keep {SLEEPER_WEIGHT}",
    }


def self_check() -> None:
    """A known weight is recovered and adopted; 0.5 is kept with no signal and when both
    sources share the same over-projection; one week cannot be held out."""
    rng = np.random.default_rng(0)
    n_weeks, per_week = 6, 400
    truth = rng.gamma(2.0, 4.0, n_weeks * per_week)
    week = np.repeat(np.arange(1, n_weeks + 1), per_week)

    def frame(ours: np.ndarray, sleeper: np.ndarray, actual: np.ndarray) -> pl.DataFrame:
        return pl.DataFrame({"week": week, "ours": ours, "sleeper": sleeper, "actual": actual})

    ours = truth + rng.normal(0, 2.0, truth.size)
    sleeper = truth + rng.normal(0, 2.0, truth.size)
    y = 0.15 * ours + 0.85 * sleeper + rng.normal(0, 1.0, truth.size)
    assert abs(fit_weight(ours, sleeper, y) - 0.85) < 0.02
    known = compare(leave_one_week_out(frame(ours, sleeper, y)))
    assert known["verdict"] == "fitted" and abs(float(known["w_mean"]) - 0.85) < 0.02, known
    y_even = truth + rng.normal(0, 3.0, truth.size)
    even = compare(leave_one_week_out(frame(ours, sleeper, y_even)))
    assert abs(float(even["w_mean"]) - 0.5) < 0.05 and even["verdict"] == f"keep {SLEEPER_WEIGHT}", even
    # both 15% high with equal information: an unconstrained fit would shrink both and "win"
    high = compare(leave_one_week_out(frame(1.15 * ours, 1.15 * sleeper, y_even)))
    assert abs(float(high["w_mean"]) - 0.5) < 0.05 and high["verdict"] == f"keep {SLEEPER_WEIGHT}", high
    assert leave_one_week_out(frame(ours, sleeper, y).filter(pl.col("week") == 1)).is_empty()
    # three weeks: the critical value is t(2), not 2
    three = compare(leave_one_week_out(frame(ours, sleeper, y).filter(pl.col("week") <= 3)))
    assert float(three["t_critical"]) > 4.0, three
    # three equally informative sources: their equal mean beats the two-source 0.5 blend
    third = truth + rng.normal(0, 2.0, truth.size)
    eq = frame(ours, sleeper, y_even).with_columns(eq=pl.Series((ours + sleeper + third) / 3))
    res = candidate(eq, "eq")
    assert res["rmse_cand"] < res["rmse_0.5"] and res["t"] < -res["t_critical"], res
    print("self-check passed: 0.85 recovered; 0.5 kept with no signal and with a shared 15% over-projection;"
          " a third source's equal mean beats the 0.5 blend")


def candidate(rows: pl.DataFrame, col: str, base: str = "half") -> dict[str, float | int | str]:
    """rows: week, ours, sleeper, actual and `col`. RMSE of `base` (the 0.5 blend, or a column)
    and of `col`, paired t over weeks on the squared-error difference (negative: `col` is better)."""
    d = rows.with_columns(half=(1 - SLEEPER_WEIGHT) * pl.col("ours") + SLEEPER_WEIGHT * pl.col("sleeper"))
    by_week = d.group_by("week").agg(
        ((pl.col(col) - pl.col("actual")) ** 2 - (pl.col(base) - pl.col("actual")) ** 2).mean().alias("x")
    )
    x = by_week["x"].to_numpy()
    ok = len(x) >= MIN_WEEKS and x.std(ddof=1) > 0
    return {
        "n": d.height,
        "weeks": len(x),
        "rmse_" + ("0.5" if base == "half" else base): round(float(((d[base] - d["actual"]) ** 2).mean() ** 0.5), 3),
        "rmse_cand": round(float(((d[col] - d["actual"]) ** 2).mean() ** 0.5), 3),
        "t": round(float(x.mean() / (x.std(ddof=1) / np.sqrt(len(x)))), 2) if ok else float("nan"),
        "t_critical": round(float(student_t.ppf(1 - ALPHA / 2, len(x) - 1)), 2) if len(x) > 1 else float("nan"),
        "weeks_better": f"{int((x < 0).sum())}/{len(x)}",
    }


# ---------- data ----------


def paired_sleeper(
    ours: pl.DataFrame, sleeper: pl.DataFrame, window: pl.DataFrame, col: str = "sleeper"
) -> pl.DataFrame:
    """For each of our picked snapshots (KEY, fetched_at), the Sleeper (or another source's
    `col`) value fetched before kickoff nearest in time to ours."""
    mine = ours.select(*KEY, _at().alias("_ours_at"))
    return (
        sleeper.with_columns(_at().alias("_at"))
        .join(window.select(*KEY, "kickoff"), on=KEY)
        .filter(pl.col("_at") < pl.col("kickoff"))
        .join(mine, on=KEY)
        .with_columns((pl.col("_at") - pl.col("_ours_at")).abs().alias("_gap"))
        .sort("_gap")
        .unique(KEY, keep="first")
        .select(*KEY, col, pl.col("_gap").dt.total_minutes().alias("pair_gap_min"))
    )


def outside_points(league: dict, games: pl.DataFrame) -> dict[str, pl.DataFrame]:
    """Each archived outside source for the games we track, scored under the league's rules, in
    the shape `_sleeper_points` returns with the value column named after the source."""
    try:
        snaps = store.read_table("outside_proj_snapshots", "archive")
    except FileNotFoundError:
        return {}
    snaps = snaps.filter(
        (pl.col("season") == int(league["season"]))
        & pl.col("week").is_in(games["week"].unique().to_list())
    )
    mapped = op.map_to_gsis(snaps, op.people()).drop_nulls("gsis_id")
    scoring = json.loads(league["scoring_settings"])
    points = store.read_table("player_points").filter(pl.col("league_id") == league["league_id"])
    stats = store.read_table("nfl_player_stats", "raw")
    out: dict[str, list[pl.DataFrame]] = {}
    for (source, season, week, _), g in mapped.group_by("source", "season", "week", "fetched_at"):
        lags = pp.lagged_means(points, stats, scoring, int(season), int(week))
        scored = pp.outside_points(g.select("source", "fetched_at", "gsis_id", "stats"), scoring, lags)
        out.setdefault(str(source), []).append(tagged(league, season, week, scored, str(source)))
    return {source: pl.concat(frames) for source, frames in out.items()}


def tagged(league: dict, season: int, week: int, rows: pl.DataFrame, col: str) -> pl.DataFrame:
    """rows (gsis_id, fetched_at, projection) in the shape `_sleeper_points` returns."""
    return rows.select(
        pl.lit(league["league_id"]).alias("league_id"), "gsis_id",
        pl.lit(season, pl.Int64).alias("season"), pl.lit(week, pl.Int64).alias("week"), "fetched_at",
        pl.col("projection").alias(col),
    )


def props_points(league: dict, games: pl.DataFrame) -> pl.DataFrame | None:
    """Prop-implied points for each week we track, as the prop_points stage computes them for the
    current week. shortcut: players are placed on their team now (Sleeper), so a player traded
    since a past week drops out of that week; fine while the archive is a few weeks long."""
    lines = pp.read_snapshots()
    if lines.is_empty():
        return None
    scoring = json.loads(league["scoring_settings"])
    schedule = store.read_table("nfl_schedules", "raw")
    points = store.read_table("player_points").filter(pl.col("league_id") == league["league_id"])
    stats = store.read_table("nfl_player_stats", "raw")
    people = pp.current_people(store.DATA_DIR)
    frames = []
    for season, week in games.select("season", "week").unique().iter_rows():
        week_games = schedule.filter((pl.col("season") == season) & (pl.col("week") == week))
        props = pp.map_players(pp.week_lines(lines, week_games), people)
        if props.is_empty():
            continue
        lags = pp.lagged_means(points, stats, scoring, season, week)
        fetched = props.group_by("gsis_id").agg(
            pl.col("stamp").max().dt.strftime("%Y-%m-%dT%H:%M:%S+00:00").alias("fetched_at")
        )
        implied = pp.implied_points(props, lags, scoring, load_config().prop_positions)
        frames.append(tagged(league, season, week, implied.join(fetched, on="gsis_id"), "props"))
    return pl.concat(frames) if frames else None


def league_rows(league: dict) -> tuple[pl.DataFrame, dict[str, int], pl.DataFrame, list[str]]:
    """Scored rows (KEY, team, position, actual, ours, sleeper, one column per outside source,
    status), the scorecard's exclusion counts, the Q/D Sleeper-0 rows of final games (actual 0
    with no stat line) and the outside sources found."""
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
    final = store.read_table("team_games").filter(pl.col("points_for").is_not_null()).select("season", "week", "team")
    window = (
        games.drop_nulls("position")
        .join(final, on=["season", "week", "team"], how="semi")
        .join(kick, on=["season", "week", "team"])
    )
    picked = _last_before_kickoff(snaps, window.select(*KEY, "kickoff"))
    ours = calibrated(
        picked.join(window.select(*KEY, "position"), on=KEY).rename({"learned": "projection"})
    ).select(*KEY, "fetched_at", pl.col("projection").alias("ours"))
    pairs = ours.join(paired_sleeper(ours, sleeper, window), on=KEY, how="left")
    outside = outside_points(league, games)
    props = props_points(league, games)
    if props is not None:
        outside["props"] = props
    for source, frame in outside.items():
        pairs = pairs.join(paired_sleeper(ours, frame, window, source).drop("pair_gap_min"), on=KEY, how="left")
    pairs = pairs.drop("fetched_at")
    scored = scored.select(*KEY, "team", "position", "actual").join(pairs, on=KEY).join(
        status, on=["gsis_id", "season", "week"], how="left"
    )
    zeroed = (
        window.select(*KEY, "position")
        .join(pairs, on=KEY)
        .join(status, on=["gsis_id", "season", "week"])
        .filter(pl.col("status").is_in(list(SLEEPER_ZEROED_STATUSES)) & (pl.col("sleeper") == 0))
        .join(points, on=KEY, how="left")
        .with_columns(pl.col("points").fill_null(0.0).alias("actual"))
    )
    return scored, excluded, zeroed, sorted(outside)


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
    rule = pl.col("p") * pl.col("ours")
    mixed = pl.col("p") * (1 - SLEEPER_WEIGHT) * pl.col("ours")
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
        scored, excluded, zeroed, sources = league_rows(league)
        print(f"\n=== {name}: scorecard exclusions {excluded}")
        blendable = scored.filter(
            pl.col("ours").is_not_null()
            & pl.col("sleeper").is_not_null()
            & ~(pl.col("status").is_in(list(SLEEPER_ZEROED_STATUSES)) & (pl.col("sleeper") == 0))
        )
        print(f"rows with both projections (production blends them): {blendable.height}, "
              f"weeks {sorted(blendable['week'].unique().to_list())}")
        if blendable.height:
            print(f"pair gap, minutes: median {blendable['pair_gap_min'].median()}, max {blendable['pair_gap_min'].max()}")
            half = (1 - SLEEPER_WEIGHT) * pl.col("ours") + SLEEPER_WEIGHT * pl.col("sleeper")
            print(
                blendable.group_by("position")
                .agg(
                    pl.len().alias("n"),
                    ((pl.col("ours") - pl.col("actual")) ** 2).mean().sqrt().alias("rmse_ours"),
                    ((pl.col("sleeper") - pl.col("actual")) ** 2).mean().sqrt().alias("rmse_sleeper"),
                    ((half - pl.col("actual")) ** 2).mean().sqrt().alias("rmse_0.5"),
                    (pl.col("ours") - pl.col("actual")).mean().alias("me_ours"),
                    (pl.col("sleeper") - pl.col("actual")).mean().alias("me_sleeper"),
                )
                .sort("position")
            )
        results = []
        per_week = blendable.group_by("position", "week").len()
        own_fit = [
            p for (p,), g in per_week.group_by("position")
            if g["len"].min() >= MIN_POSITION_WEEK_ROWS
            and g.height == blendable["week"].n_unique()
        ]
        for pos in ["ALL (verdict)", *sorted(own_fit)]:
            rows = blendable if pos.startswith("ALL") else blendable.filter(pl.col("position") == pos)
            held = leave_one_week_out(rows.select("week", "ours", "sleeper", "actual"))
            results.append(
                {"position": pos, **compare(held)}
                if held.height
                else {"position": pos, "n": rows.height, "verdict": "untestable: fewer than 2 weeks"}
            )
        print(pl.DataFrame(results))
        if sources and blendable.height:
            eq = blendable.with_columns(pl.mean_horizontal("ours", "sleeper", *sources).alias("eq_all"))
            counts = {s: int(eq[s].is_not_null().sum()) for s in sources}
            print(f"shipped blend: equal-weight mean of every source a row has (rows with each source {counts})")
            print(pl.DataFrame([{"position": "ALL", "against": "old 0.5", **candidate(eq, "eq_all")}]))
            print(pl.DataFrame([{"position": "ALL", "against": "ours", **candidate(eq, "eq_all", "ours")}]))
        rates = status_play_rates(league["league_id"])
        print(f"Q/D Sleeper-0 rule (status play rates {({k: round(v, 3) for k, v in rates.items()})}):",
              score_zero_rule(zeroed, rates))
    print("\nThe two leagues score the same games: read their verdicts as one test, not two.")


if __name__ == "__main__":
    main()
