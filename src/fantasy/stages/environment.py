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
from typing import NamedTuple

import nflreadpy
import numpy as np
import polars as pl

from fantasy import store
from fantasy.sim.injuries import InjuryModel
from fantasy.sim.scoring_scale import reference_league
from fantasy.stages.crosswalk import normalize_name
from fantasy.stages.distributions import calibrated
from fantasy.stages.outlook import build_panel

HALF_LIFE = 6.0  # games
WINDOW = 17  # games
SHRINK = 1.0  # pseudo-games at the league average
MIN_GAMES_CB = 4  # a team needs this many games before its leading corners are known
CB_LEADERS = 2
MIN_T = 2.0
TTL_HOURS = 12.0
RIDGE = 1.0
SKILL = ["QB", "RB", "WR", "TE"]
CONTROLS = ["first_back", "second_back", "vac_target", "vac_carry", "log_context"]
FEATURES = ["pass_epa", "sack_rate", "cb_out"]
KINDS = {"pass_epa": "team_pass_epa", "sack_rate": "team_sack_rate", "cb_out": "opp_cb_out"}
LATEST = 99  # the "week" that holds a team's rating after its latest game


class Live(NamedTuple):
    """The current situation for `sim/environment.py`."""

    team_z: dict[str, tuple[float, float]]  # team -> (pass efficiency z, sack rate z)
    cb_absent: dict[tuple[str, int], float]  # (team, week) -> expected leading corners out
    opponent: dict[tuple[str, int], str]  # (team, week) -> opponent


def team_efficiency(seasons: range) -> pl.DataFrame:
    """Per team-game: offense pass EPA per dropback and sack rate, from play-by-play."""
    frames = []
    for season in seasons:
        pbp = nflreadpy.load_pbp(season)
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
    table = team_efficiency(range(2018, season + 1)).select(*store.SCHEMAS["nfl_team_efficiency"])
    store.write_table("nfl_team_efficiency", table, "raw")
    return table


def ratings(table: pl.DataFrame) -> pl.DataFrame:
    """Each team's rating before each game (season, week, team, pass_epa, sack_rate, and `*_z`
    scaled by the spread of ratings) and the same after its latest game (week LATEST).

    A rating is the exponentially weighted average of the team's recent games minus the league
    average, pulled toward zero by SHRINK pseudo-games."""
    centre = (
        float(np.nanmean(table["pass_epa"].to_numpy())),
        float(np.nanmean(table["sack_rate"].to_numpy())),
    )
    rows = []
    for (team,), g in table.sort("season", "week").group_by("team", maintain_order=True):
        series = (g["pass_epa"].to_numpy() - centre[0], g["sack_rate"].to_numpy() - centre[1])
        for i in range(len(g) + 1):
            lo = max(0, i - WINDOW)
            weights = 0.5 ** (np.arange(i - lo)[::-1] / HALF_LIFE)
            values = [
                float((weights * s[lo:i]).sum() / (weights.sum() + SHRINK)) if i > lo else 0.0
                for s in series
            ]
            season, week = (
                (int(g["season"][i]), int(g["week"][i]))
                if i < len(g)
                else (int(g["season"][-1]), LATEST)
            )
            rows.append((season, week, team, values[0], values[1]))
    out = pl.DataFrame(
        rows, schema=["season", "week", "team", "pass_epa", "sack_rate"], orient="row"
    )
    spread = {c: float(np.std(out[c].to_numpy(), ddof=1)) or 1.0 for c in ("pass_epa", "sack_rate")}
    return out.with_columns(
        (pl.col("pass_epa") / spread["pass_epa"]).alias("pass_epa_z"),
        (pl.col("sack_rate") / spread["sack_rate"]).alias("sack_rate_z"),
    )


def _name(column: str) -> pl.Expr:
    return pl.col(column).map_elements(normalize_name, return_dtype=pl.String).alias("nm")


def _leading_cbs(snaps: pl.DataFrame, injuries: pl.DataFrame) -> pl.DataFrame:
    """Per team-week: the leading CB_LEADERS corners by defense snaps in earlier weeks of the
    season, and whether each is listed Out or Doubtful that week (the report is final by
    Friday). Columns: season, week, team, nm, out."""
    snaps = snaps.filter(pl.col("game_id").is_not_null()).with_columns(_name("player"))
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
        .with_columns(_name("full_name"))
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
            records += [
                {"position": position, "kind": KINDS[k], "value": 0.0, "t": 0.0, "n": rows.height}
                for k in FEATURES
            ]
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


def live_cb_absent(
    snaps: pl.DataFrame,
    injuries: pl.DataFrame,
    team_games: pl.DataFrame,
    model: InjuryModel | None,
    season: int,
    current_week: int,
) -> dict[tuple[str, int], float]:
    """Expected number of each team's leading corners out in its coming games.

    Leading corners are the top CB_LEADERS by defense snaps in games before this week. A
    corner on the latest injury report gets a chance of playing each game from the injury
    model (the same curves as skill players, an approximation); without a model, Out and
    Doubtful count as out this week only."""
    before = snaps.filter((pl.col("season") == season) & (pl.col("week") < current_week))
    if before.is_empty():
        return {}
    ranked = (
        before.filter((pl.col("position") == "CB") & pl.col("game_id").is_not_null())
        .with_columns(_name("player"))
        .group_by("team", "nm")
        .agg(pl.col("defense_snaps").fill_null(0.0).sum().alias("snaps"))
        .with_columns(pl.col("snaps").rank("ordinal", descending=True).over("team").alias("rk"))
        .filter(pl.col("rk") <= CB_LEADERS)
    )
    games_played = before.group_by("team").agg(pl.col("week").n_unique().alias("games"))
    ready = set(games_played.filter(pl.col("games") >= MIN_GAMES_CB - 1)["team"])
    latest = (
        injuries.filter((pl.col("season") == season) & (pl.col("week") <= current_week))
        .with_columns(_name("full_name"))
        .sort("week")
        .group_by("team", "nm")
        .agg(
            pl.col("report_status").last().alias("status"),
            pl.coalesce("report_primary_injury", "practice_primary_injury").last().alias("body"),
        )
    )
    flagged = {(r["team"], r["nm"]): (r["status"], r["body"]) for r in latest.iter_rows(named=True)}
    coming = (
        team_games.filter((pl.col("season") == season) & (pl.col("week") >= current_week))
        .select("team", "week")
        .sort("team", "week")
    )
    weeks_of: dict[str, list[int]] = {}
    for team, week in coming.iter_rows():
        weeks_of.setdefault(team, []).append(week)
    out: dict[tuple[str, int], float] = {}
    for team, nm in zip(ranked["team"], ranked["nm"], strict=True):
        status, body = flagged.get((team, nm), (None, None))
        if team not in ready or status not in ("Out", "Doubtful", "Questionable"):
            continue
        curve = model.curve((status, body, None)) if model else None
        chances = curve[0] if curve else ((0.0,) if status in ("Out", "Doubtful") else ())
        for k, week in enumerate(weeks_of.get(team, [])):
            if k >= len(chances):
                break
            out[(team, week)] = out.get((team, week), 0.0) + (1.0 - chances[k])
    return out


def live(
    efficiency: pl.DataFrame,
    snaps: pl.DataFrame,
    injuries: pl.DataFrame,
    team_games: pl.DataFrame,
    model: InjuryModel | None,
    season: int,
    current_week: int,
) -> Live:
    latest = ratings(efficiency).filter(pl.col("week") == LATEST)
    team_z = {r["team"]: (r["pass_epa_z"], r["sack_rate_z"]) for r in latest.iter_rows(named=True)}
    games = team_games.filter(pl.col("season") == season)
    opponent = {
        (r["team"], r["week"]): r["opponent"]
        for r in games.select("team", "week", "opponent").iter_rows(named=True)
    }
    cb = live_cb_absent(snaps, injuries, team_games, model, season, current_week)
    return Live(team_z, cb, opponent)


def run() -> int:
    leagues = store.read_table("leagues", "raw")
    league_id = reference_league(leagues)  # point effects are scaled to the other league later
    season = int(leagues["season"].to_numpy().max())
    efficiency = load_efficiency(season)
    stats = store.read_table("nfl_player_stats", "raw")
    injuries = store.read_table("nfl_injuries", "raw").filter(pl.col("season") < season)
    opponents = stats.filter(pl.col("season_type") == "REG").select(
        pl.col("player_id").alias("gsis_id"), "season", "week", "opponent_team"
    )
    baseline = calibrated(
        store.read_table("proj_baseline").filter(
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
    panel = build_panel_env(
        panel,
        ratings(efficiency.filter(pl.col("season") < season)),
        cb_out_table(store.read_table("nfl_snaps", "raw"), injuries),
    )
    table = estimate(panel)
    store.write_table("environment_effects", table)
    return table.height


if __name__ == "__main__":
    print(f"{run()} rows")
