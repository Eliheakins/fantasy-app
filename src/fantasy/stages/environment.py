"""Measure how a player's offense and his opponent's injuries change his projection.

Tested against walk-forward projections 2019 to 2025 (see docs/decisions.md), net of the return,
vacancy and size effects already modeled:
  * team_pass_epa, team_sack_rate: an offense's recent pass efficiency and sack rate (per team,
    moving average over about six games, centered and scaled to unit spread) mean-revert, so
    players on high-efficiency offenses fall a little short of projection and players on
    heavily sacked offenses beat theirs. This is not "good lines lift players": the baseline's
    player form already carries team quality, and the team numbers are partly noise.
  * opp_cb_out: each of the opponent's two leading cornerbacks (by snaps this season) who is out
    or doubtful lifts the quarterback and receivers.
Tested and not shipped: offensive line starters out (no effect on QB, RB or WR), opposing
safeties, defensive linemen and linebackers out, opponent pass or rush efficiency, a starting
quarterback out, a slot-corner bump (free data has no alignment).

`estimate` writes `environment_effects` (position, kind, value, t, n); a kind is applied only
where |t| is at least MIN_T. `live` reads the current situation for `sim/environment.py`.

Run: uv run python -m fantasy.stages.environment
"""

import time

import numpy as np
import polars as pl

from fantasy import store
from fantasy.sim.calibration import calibrated
from fantasy.sim.environment import CB_LEADERS, MIN_GAMES_CB, name_column, ratings
from fantasy.sim.scoring_scale import reference_league
from fantasy.stages.outlook import build_panel
from fantasy.store import SKILL
from nfl_stat.core.seasons import FANTASY_FIRST_SEASON
from nfl_stat.pipeline.pbp_source import read_pbp

MIN_T = 2.0
REPLICATE_T = 1.0  # each half of the history must show the same sign with at least this |t|
SPLIT_SEASON = 2024  # the halves are before this season and from it on
TTL_HOURS = 12.0
RIDGE = 1.0
CONTROLS = ["first_back", "second_back", "vac_target", "vac_carry", "log_context"]
FEATURES = ["pass_epa", "sack_rate", "cb_out"]
KINDS = {"pass_epa": "team_pass_epa", "sack_rate": "team_sack_rate", "cb_out": "opp_cb_out"}
EFFICIENCY_COLUMNS = ["season", "week", "season_type", "posteam", "defteam", "pass", "epa", "sack"]


def team_efficiency(seasons: range) -> pl.DataFrame:
    """Per team-game: offense pass EPA per dropback and sack rate, from play-by-play."""
    frames = []
    for season in seasons:
        pbp = read_pbp(season, EFFICIENCY_COLUMNS)
        plays = pbp.filter(
            (pl.col("season_type") == "REG")
            & pl.col("epa").is_not_null()
            & pl.col("posteam").is_not_null()
            & (pl.col("pass") == 1)
        )
        frames.append(
            plays.group_by("season", "week", "posteam", "defteam").agg(
                pl.col("epa").mean().alias("pass_epa"), pl.col("sack").mean().alias("sack_rate")
            )
        )
    return (
        pl.concat(frames)
        .rename({"posteam": "team", "defteam": "opponent"})
        .with_columns(pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64))
    )


def load_efficiency(season: int) -> pl.DataFrame:
    """The team-game table, refreshed from play-by-play at most every TTL_HOURS."""
    path = store.table_path("nfl_team_efficiency", "raw")
    if path.exists() and (time.time() - path.stat().st_mtime) / 3600 < TTL_HOURS:
        return store.read_table("nfl_team_efficiency", "raw")
    table = team_efficiency(range(FANTASY_FIRST_SEASON, season + 1)).select(
        *store.SCHEMAS["nfl_team_efficiency"]
    )
    store.write_table("nfl_team_efficiency", table, "raw")
    return table


def _leading_cbs(snaps: pl.DataFrame, injuries: pl.DataFrame) -> pl.DataFrame:
    """Per team-week: the leading CB_LEADERS corners by defense snaps in earlier weeks of the
    season, and whether each is listed Out or Doubtful that week (the report is final by
    Friday). Columns: season, week, team, nm, out."""
    snaps = snaps.filter(pl.col("game_id").is_not_null()).with_columns(name_column("player"))
    weeks = snaps.select("season", "week", "team").unique()
    cbs = (
        snaps.filter(pl.col("position") == "CB")
        .select("season", "week", "team", "nm", pl.col("defense_snaps").fill_null(0.0).alias("sn"))
        .sort("season", "team", "nm", "week")
    )
    cumulative = cbs.with_columns(pl.col("sn").cum_sum().over("season", "team", "nm").alias("cum"))
    cum = (
        weeks.join(cbs.select("season", "team", "nm").unique(), on=["season", "team"])
        .join(
            cumulative.select("season", "team", "nm", "week", "cum"),
            on=["season", "team", "nm", "week"],
            how="left",
        )
        .sort("season", "team", "nm", "week")
        .with_columns(pl.col("cum").forward_fill().over("season", "team", "nm").fill_null(0.0))
        .with_columns(
            pl.col("cum").shift(1).over("season", "team", "nm").fill_null(0.0).alias("prior")
        )
    )
    top = cum.with_columns(
        pl.col("prior").rank("ordinal", descending=True).over("season", "team", "week").alias("rk")
    ).filter((pl.col("rk") <= CB_LEADERS) & (pl.col("week") >= MIN_GAMES_CB))
    listed = (
        injuries.filter(
            (pl.col("game_type") == "REG") & pl.col("report_status").is_in(["Out", "Doubtful"])
        )
        .with_columns(name_column("full_name"))
        .select("season", "week", "team", "nm")
        .unique()
        .with_columns(pl.lit(True).alias("out"))
    )
    return (
        top.join(listed, on=["season", "week", "team", "nm"], how="left")
        .with_columns(pl.col("out").fill_null(False))
        .select("season", "week", "team", "nm", "out")
    )


def cb_out_table(snaps: pl.DataFrame, injuries: pl.DataFrame) -> pl.DataFrame:
    """Per team-week: how many of the leading corners are out or doubtful."""
    return (
        _leading_cbs(snaps, injuries)
        .group_by("season", "week", "team")
        .agg(pl.col("out").sum().cast(pl.Float64).alias("cb_out"))
    )


def build_panel_env(
    base: pl.DataFrame, efficiency_ratings: pl.DataFrame, cb: pl.DataFrame
) -> pl.DataFrame:
    """The outlook panel (miss, returns, vacancy) plus this offense's ratings and the opposing
    corners out. `base` must carry `opponent_team` and `context`."""
    own = efficiency_ratings.select("season", "week", "team", "pass_epa_z", "sack_rate_z")
    opposing = cb.rename({"team": "opponent_team"})
    return (
        base.join(own, on=["season", "week", "team"], how="left")
        .join(opposing, on=["season", "week", "opponent_team"], how="left")
        .with_columns(
            pl.col("pass_epa_z").fill_null(0.0).alias("pass_epa"),
            pl.col("sack_rate_z").fill_null(0.0).alias("sack_rate"),
            pl.col("cb_out").fill_null(0.0),
            pl.col("first_back").cast(pl.Float64),
            pl.col("second_back").cast(pl.Float64),
            pl.col("context").fill_null(1.0).log().alias("log_context"),
        )
    )


def estimate(panel: pl.DataFrame) -> pl.DataFrame:
    """The environment_effects table: for each position and kind, points per unit (per standard
    deviation for the two team ratings, per corner out), the robust t-statistic and n."""
    records = []
    cols = [*CONTROLS, *FEATURES]
    for position in SKILL:
        rows = panel.filter(pl.col("position") == position)
        if rows.height < len(cols) + 31:
            # no row, not a measured zero: the simulation then applies no effect, and a thin or
            # broken panel is told apart from a real null effect
            print(f"environment: {position} has {rows.height} rows, too few; no effects stored")
            continue
        x = np.column_stack(
            [rows[c].to_numpy().astype(float) for c in cols] + [np.ones(rows.height)]
        )
        y = rows["miss"].to_numpy()
        penalty = RIDGE * np.eye(x.shape[1])
        penalty[-1, -1] = 0.0
        inverse = np.linalg.inv(x.T @ x + penalty)
        beta = inverse @ x.T @ y
        resid = y - x @ beta
        se = np.sqrt(np.diag(inverse @ (x.T * (resid**2)) @ x @ inverse))
        for kind in FEATURES:
            j = cols.index(kind)
            records.append(
                {
                    "position": position,
                    "kind": KINDS[kind],
                    "value": float(beta[j]),
                    "t": float(beta[j] / se[j]) if se[j] > 0 else 0.0,
                    "n": rows.height,
                }
            )
    return pl.DataFrame(records, schema=store.SCHEMAS["environment_effects"])


def history_panel(league_id: str, season: int) -> pl.DataFrame:
    """Player-game panel for every season before `season`, with environment features."""
    efficiency = load_efficiency(season)
    stats = store.read_table("nfl_player_stats", "raw")
    injuries = store.read_table("nfl_injuries", "raw").filter(pl.col("season") < season)
    opponents = stats.filter(pl.col("season_type") == "REG").select(
        pl.col("player_id").alias("gsis_id"), "season", "week", "opponent_team"
    )
    baseline = calibrated(
        store.projection_table().filter(
            (pl.col("league_id") == league_id)
            & ~pl.col("is_future")
            & pl.col("has_history")
            & (pl.col("season") < season)
        )
    ).select("league_id", "gsis_id", "season", "week", "position", "team", "projection", "context")
    panel = build_panel(
        stats,
        store.read_table("nfl_team_stats", "raw"),
        injuries,
        store.read_table("team_games"),
        store.read_table("player_points")
        .filter(pl.col("league_id") == league_id)
        .select("gsis_id", "season", "week", "points"),
        baseline.select("gsis_id", "season", "week", "position", "team", "projection"),
    )
    panel = panel.join(
        baseline.select("gsis_id", "season", "week", "context"), on=["gsis_id", "season", "week"]
    ).join(opponents, on=["gsis_id", "season", "week"], how="left")
    return build_panel_env(
        panel,
        ratings(efficiency.filter(pl.col("season") < season)),
        cb_out_table(store.read_table("nfl_snaps", "raw"), injuries),
    )


def replicated(full: pl.DataFrame, early: pl.DataFrame, late: pl.DataFrame) -> pl.DataFrame:
    """`full` with t set to 0 for every effect that does not show up in both halves of the history
    with the same sign (the |t| of 2 cut is chosen on the same data the effect is fit on)."""
    keys = ["position", "kind"]
    halves = early.select(*keys, e_value="value", e_t="t").join(
        late.select(*keys, l_value="value", l_t="t"), on=keys
    )
    joined = full.join(halves, on=keys, how="left")
    holds = (
        (pl.col("value").sign() == pl.col("e_value").sign())
        & (pl.col("value").sign() == pl.col("l_value").sign())
        & (pl.col("e_t").abs() >= REPLICATE_T)
        & (pl.col("l_t").abs() >= REPLICATE_T)
    ).fill_null(False)
    return joined.with_columns(t=pl.when(holds).then(pl.col("t")).otherwise(0.0)).select(
        full.columns
    )


def run() -> int:
    leagues = store.read_table("leagues", "raw")
    league_id = reference_league(leagues)  # point effects are scaled to the other league later
    season = int(leagues["season"].to_numpy().max())
    panel = history_panel(league_id, season)
    table = replicated(
        estimate(panel),
        estimate(panel.filter(pl.col("season") < SPLIT_SEASON)),
        estimate(panel.filter(pl.col("season") >= SPLIT_SEASON)),
    )
    store.write_table("environment_effects", table)
    return table.height


if __name__ == "__main__":
    print(f"{run()} rows")
