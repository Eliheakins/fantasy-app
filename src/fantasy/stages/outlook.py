"""Measure two in-season changes our baseline projection misses, and read the live situation.

Walk-forward projections 2019 to 2025 against actual points show two systematic misses:
  * a player in his first game back after missing a team game scores about 60% (QB), 75% (RB),
    79% (TE) and 74% (WR) of his projection, and 87% to 95% in the second game back;
  * when teammates who carry a share of the targets or carries are out, the receivers and backs
    who remain beat their projections, by about 3 points per unit of vacated share.
Usage trends, opponent strength and rookie status add nothing out of sample on top of the
baseline (see docs/decisions.md), so they are not modeled.

`estimate` writes `outlook_effects` (position, kind, value, n). `live_context` reads who is
returning this week and each player's recent target and carry share, for `sim/outlook.py`.

Run: uv run python -m fantasy.stages.outlook
"""

import numpy as np
import polars as pl

from fantasy import store
from fantasy.sim.outlook import MIN_SHARE, Context
from fantasy.sim.scoring_scale import reference_league
from fantasy.stages.distributions import calibrated
from fantasy.store import SKILL, week_index

HALF_LIFE = 4.0  # games, for the usage averages
RIDGE = 1.0
MIN_PROJECTION = 2.0  # below this a projection is a depth player and the ratios are unstable


def usage_table(stats: pl.DataFrame, team_stats: pl.DataFrame) -> pl.DataFrame:
    """Per player-game: target and carry share, and their exponentially weighted averages
    (`*_ewma` includes the game, `*_prior` stops before it)."""
    team_carries = team_stats.filter(pl.col("season_type") == "REG").select(
        "team", "season", "week", pl.col("carries").alias("team_carries")
    )
    rows = (
        stats.filter(pl.col("season_type") == "REG")
        .select(
            pl.col("player_id").alias("gsis_id"),
            "season",
            "week",
            "team",
            "target_share",
            "carries",
        )
        .join(team_carries, on=["team", "season", "week"], how="left")
        .with_columns(
            pl.col("target_share").fill_null(0.0),
            (pl.col("carries").fill_null(0.0) / pl.col("team_carries"))
            .fill_null(0.0)
            .alias("carry_share"),
        )
        .sort("gsis_id", "season", "week")
    )
    rows = rows.with_columns(
        pl.col("target_share").ewm_mean(half_life=HALF_LIFE).over("gsis_id").alias("target_ewma"),
        pl.col("carry_share").ewm_mean(half_life=HALF_LIFE).over("gsis_id").alias("carry_ewma"),
    )
    return rows.with_columns(
        pl.col("target_ewma").shift(1).over("gsis_id").alias("target_prior"),
        pl.col("carry_ewma").shift(1).over("gsis_id").alias("carry_prior"),
    )


def build_panel(
    stats: pl.DataFrame,
    team_stats: pl.DataFrame,
    injuries: pl.DataFrame,
    team_games: pl.DataFrame,
    points: pl.DataFrame,
    baseline: pl.DataFrame,
) -> pl.DataFrame:
    """One row per projected player-game with the miss (points minus projection), whether it was
    a first or second game back, and the target and carry share vacated by absent teammates."""
    usage = usage_table(stats, team_stats)
    games = store.team_game_index(team_games)
    panel = (
        baseline.join(points, on=["gsis_id", "season", "week"], how="inner")
        .join(games, on=["team", "season", "week"], how="left")
        .sort("gsis_id", "season", "week")
        .with_columns(
            (pl.col("points") - pl.col("projection")).alias("miss"),
            # gaps are measured before the projection filter, or a skipped low-projection game
            # would look like an absence
            (pl.col("g") - pl.col("g").shift(1).over("gsis_id", "season") - 1)
            .fill_null(0)
            .alias("missed"),
            pl.col("week").shift(1).over("gsis_id", "season").alias("prev_week"),
        )
        .filter(pl.col("projection") > MIN_PROJECTION)
    )
    # an absence is an injury absence if the player was on the report around the games he missed
    listed = (
        injuries.filter(pl.col("game_type") == "REG").select("gsis_id", "season", "week").unique()
    )
    gaps = panel.filter(pl.col("missed") >= 1).select("gsis_id", "season", "week", "prev_week")
    reported = (
        gaps.join(listed.rename({"week": "listed_week"}), on=["gsis_id", "season"])
        .filter(
            (pl.col("listed_week") >= pl.col("prev_week") - 1)
            & (pl.col("listed_week") < pl.col("week"))
        )
        .select("gsis_id", "season", "week")
        .unique()
        .with_columns(pl.lit(True).alias("injured_gap"))
    )
    panel = (
        panel.join(reported, on=["gsis_id", "season", "week"], how="left")
        .with_columns(pl.col("injured_gap").fill_null(False))
        .with_columns(
            (pl.col("missed") >= 1).alias("first_back"),
            ((pl.col("missed") == 0) & (pl.col("missed").shift(1).over("gsis_id", "season") >= 1))
            .fill_null(False)
            .alias("second_back"),
            pl.col("injured_gap")
            .shift(1)
            .over("gsis_id", "season")
            .fill_null(False)
            .alias("prev_injured"),
        )
    )
    # share carried by teammates reported Out or Doubtful, from their usage the week before
    out = (
        injuries.filter(
            pl.col("position").is_in(SKILL)
            & (pl.col("game_type") == "REG")
            & pl.col("report_status").is_in(["Out", "Doubtful"])
        )
        .select("gsis_id", "team", "season", "week")
        .with_columns(week_index().alias("t"))
        .sort("t")
    )
    latest = usage.select(
        "gsis_id",
        (week_index() + 1).alias("t"),
        "target_ewma",
        "carry_ewma",
    ).sort("t")
    gone = out.join_asof(
        latest, on="t", by="gsis_id", strategy="backward", check_sortedness=False
    ).drop_nulls("target_ewma")
    gone = gone.filter(
        (pl.col("target_ewma") > MIN_SHARE[0]) | (pl.col("carry_ewma") > MIN_SHARE[1])
    )
    vacated = gone.group_by("team", "season", "week").agg(
        pl.col("target_ewma").sum().alias("vac_target"),
        pl.col("carry_ewma").sum().alias("vac_carry"),
    )
    return panel.join(vacated, on=["team", "season", "week"], how="left").with_columns(
        pl.col("vac_target").fill_null(0.0), pl.col("vac_carry").fill_null(0.0)
    )


def _ridge(design: np.ndarray, y: np.ndarray) -> np.ndarray | None:
    """Ridge coefficients, or None when there are too few rows to estimate anything."""
    if design.shape[0] < design.shape[1]:
        return None
    penalty = RIDGE * np.eye(design.shape[1])
    penalty[-1, -1] = 0.0  # leave the intercept alone
    return np.linalg.solve(design.T @ design + penalty, design.T @ y)


def estimate(panel: pl.DataFrame) -> pl.DataFrame:
    """The outlook_effects table: position, kind, value (a ratio for the two return kinds, points
    per unit of vacated share for the two vacancy kinds) and n."""
    records = []
    for position in SKILL:
        rows = panel.filter(pl.col("position") == position)
        for kind, mask in (
            ("first_back_injury", pl.col("first_back") & pl.col("injured_gap")),
            ("first_back_other", pl.col("first_back") & ~pl.col("injured_gap")),
            ("second_back_injury", pl.col("second_back") & pl.col("prev_injured")),
            ("second_back_other", pl.col("second_back") & ~pl.col("prev_injured")),
        ):
            hit = rows.filter(mask)
            projected = float(hit["projection"].to_numpy().sum()) if hit.height else 0.0
            if not projected:  # no row rather than a ratio of 1.0: an empty cell is not measured
                print(f"outlook: {position} {kind} has no games; no effect stored")
                continue
            ratio = float(hit["points"].to_numpy().sum()) / projected
            records.append({"position": position, "kind": kind, "value": ratio, "n": hit.height})
        # vacancy slopes on games that are not a return, so the two effects stay separate
        base = rows.filter(~pl.col("first_back") & ~pl.col("second_back"))
        design = np.column_stack(
            [base["vac_target"].to_numpy(), base["vac_carry"].to_numpy(), np.ones(base.height)]
        )
        beta = _ridge(design, base["miss"].to_numpy())
        if beta is None:
            print(f"outlook: {position} has {base.height} rows, too few; no vacancy effects stored")
            continue
        for kind, value in (("vac_target", beta[0]), ("vac_carry", beta[1])):
            records.append(
                {"position": position, "kind": kind, "value": float(value), "n": base.height}
            )
    return pl.DataFrame(records, schema=store.SCHEMAS["outlook_effects"])


def live_context(
    stats: pl.DataFrame,
    team_stats: pl.DataFrame,
    team_games: pl.DataFrame,
    injuries: pl.DataFrame,
    season: int,
    current_week: int,
) -> Context:
    """Who is back this week, and each player's latest usage, from games before `current_week`.

    A missed stretch counts as an injury absence when the player was on the injury report in the
    week before it began or during it."""
    usage = usage_table(stats.filter(pl.col("season") <= season), team_stats)
    played = usage.filter((pl.col("season") == season) & (pl.col("week") < current_week))
    games = (
        team_games.filter((pl.col("game_type") == "REG") & (pl.col("season") == season))
        .select("team", "week")
        .filter(pl.col("week") < current_week)
        .sort("team", "week")
        .with_columns(pl.int_range(pl.len()).over("team").alias("g"))
    )
    seen = played.join(games, on=["team", "week"], how="inner").sort("gsis_id", "week")
    team_last = games.group_by("team").agg(pl.col("g").max().alias("team_last"))
    per_player = (
        seen.group_by("gsis_id")
        .agg(
            pl.col("g").last().alias("last_g"),
            pl.col("g").diff().last().alias("last_gap"),
            pl.col("week").last().alias("last_week"),
            pl.col("week").shift(1).last().alias("prev_week"),
            pl.col("team").last().alias("team"),
        )
        .join(team_last, on="team")
        .with_columns((pl.col("team_last") - pl.col("last_g")).alias("missed"))
    )
    listed: dict[str, set[int]] = {}
    reports = injuries.filter((pl.col("season") == season) & (pl.col("game_type") == "REG"))
    for g, week in zip(reports["gsis_id"], reports["week"], strict=True):
        listed.setdefault(g, set()).add(week)

    def reported(gsis_id: str, low: int, high: int) -> bool:
        return any(low <= w <= high for w in listed.get(gsis_id, ()))

    missed: dict[str, tuple[int, bool]] = {}
    after: dict[str, bool] = {}
    for r in per_player.iter_rows(named=True):
        g = r["gsis_id"]
        if r["missed"] >= 1:
            missed[g] = (int(r["missed"]), reported(g, r["last_week"] - 1, current_week - 1))
        elif r["last_gap"] is not None and r["last_gap"] >= 2 and r["prev_week"] is not None:
            after[g] = reported(g, r["prev_week"] - 1, r["last_week"] - 1)
    latest = (
        usage.sort("gsis_id", "season", "week")
        .group_by("gsis_id")
        .agg(pl.col("team").last(), pl.col("target_ewma").last(), pl.col("carry_ewma").last())
    )
    shares = {
        r["gsis_id"]: (r["team"], float(r["target_ewma"]), float(r["carry_ewma"]))
        for r in latest.iter_rows(named=True)
    }
    return Context(missed, after, shares)


def history_panel(league_id: str, season: int) -> pl.DataFrame:
    """Player-game panel for every season before `season`."""
    return build_panel(
        store.read_table("nfl_player_stats", "raw"),
        store.read_table("nfl_team_stats", "raw"),
        store.read_table("nfl_injuries", "raw").filter(pl.col("season") < season),
        store.read_table("team_games"),
        store.read_table("player_points")
        .filter(pl.col("league_id") == league_id)
        .select("gsis_id", "season", "week", "points"),
        calibrated(
            store.projection_table().filter(
                (pl.col("league_id") == league_id)
                & ~pl.col("is_future")
                & pl.col("has_history")
                & (pl.col("season") < season)
            )
        ).select("gsis_id", "season", "week", "position", "team", "projection"),
    )


def run() -> int:
    leagues = store.read_table("leagues", "raw")
    league_id = reference_league(leagues)  # point effects are scaled to the other league later
    season = int(leagues["season"].to_numpy().max())
    table = estimate(history_panel(league_id, season))
    store.write_table("outlook_effects", table)
    return table.height


if __name__ == "__main__":
    print(f"{run()} rows")
