"""Adjust projections for the offense a player is on and the injuries on the defense he faces.

Two kinds of effect, measured in `stages/environment.py` and applied only where the estimate is
clear (|t| of at least MIN_T):
  * the offense's recent sack rate and pass efficiency (per standard deviation across teams):
    these mean-revert, so a heavily sacked offense's players beat their projections a little and
    a very efficient offense's fall short;
  * each of the opponent's two leading cornerbacks who is out lifts quarterbacks and receivers.

The adjustment is added to points-when-playing, so a player's `projection` still means expected
points counting the chance of not playing and `play_prob` the chance of playing.
"""

from typing import NamedTuple

import numpy as np
import polars as pl

from fantasy.sim.injuries import InjuryModel
from fantasy.sim.scoring_scale import Effects
from fantasy.teams import SUFFIXES

MIN_T = 2.0
HALF_LIFE = 6.0  # games
WINDOW = 17  # games
SHRINK = 1.0  # pseudo-games at the league average
MIN_GAMES_CB = 4  # a team needs this many games before its leading corners are known
CB_LEADERS = 2
LATEST = 99  # the "week" that holds a team's rating after its latest game


class Situation(NamedTuple):
    """The current situation: team ratings, expected opposing corners out, and the schedule."""

    team_z: dict[str, tuple[float, float]]  # team -> (pass efficiency z, sack rate z)
    cb_absent: dict[tuple[str, int], float]  # (team, week) -> expected leading corners out
    opponent: dict[tuple[str, int], str]  # (team, week) -> opponent


def effects_dict(table: pl.DataFrame, min_t: float = MIN_T) -> Effects:
    """The clear effects only: those with |t| of at least `min_t`."""
    return {
        (r["position"], r["kind"]): r["value"]
        for r in table.iter_rows(named=True)
        if abs(r["t"]) >= min_t
    }


def apply_environment(
    projections: pl.DataFrame, situation: Situation, effects: Effects, current_week: int
) -> pl.DataFrame:
    """`projections` (gsis_id, week, projection, play_prob, team, position) with the team and
    opposing-corner effects applied, plus `offense_points` and `matchup_points` columns. A
    projection never goes below zero."""
    offense, matchup = [], []
    for team, position, week in zip(
        projections["team"], projections["position"], projections["week"], strict=True
    ):
        if week < current_week:
            offense.append(0.0)
            matchup.append(0.0)
            continue
        pass_z, sack_z = situation.team_z.get(team, (0.0, 0.0))
        offense.append(
            effects.get((position, "team_pass_epa"), 0.0) * pass_z
            + effects.get((position, "team_sack_rate"), 0.0) * sack_z
        )
        opponent = situation.opponent.get((team, week))
        absent = situation.cb_absent.get((opponent, week), 0.0) if opponent else 0.0
        matchup.append(effects.get((position, "opp_cb_out"), 0.0) * absent)
    return projections.with_columns(
        pl.Series("offense_points", offense, dtype=pl.Float64),
        pl.Series("matchup_points", matchup, dtype=pl.Float64),
    ).with_columns(
        (
            pl.col("projection")
            + pl.col("play_prob") * (pl.col("offense_points") + pl.col("matchup_points"))
        )
        .clip(lower_bound=0.0)
        .alias("projection")
    )


class Live(NamedTuple):
    """The current situation for `sim/environment.py`."""

    team_z: dict[str, tuple[float, float]]  # team -> (pass efficiency z, sack rate z)
    cb_absent: dict[tuple[str, int], float]  # (team, week) -> expected leading corners out
    opponent: dict[tuple[str, int], str]  # (team, week) -> opponent


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


def name_column(column: str) -> pl.Expr:
    """Vectorized `normalize_name`: lowercase letters and spaces only, no name suffixes."""
    return (
        pl.col(column)
        .str.to_lowercase()
        .str.replace_all(r"[^a-z ]", "")
        .str.split(" ")
        .list.eval(pl.element().filter((pl.element() != "") & ~pl.element().is_in(list(SUFFIXES))))
        .list.join(" ")
        .alias("nm")
    )


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
        .with_columns(name_column("player"))
        .group_by("team", "nm")
        .agg(pl.col("defense_snaps").fill_null(0.0).sum().alias("snaps"))
        .with_columns(pl.col("snaps").rank("ordinal", descending=True).over("team").alias("rk"))
        .filter(pl.col("rk") <= CB_LEADERS)
    )
    games_played = before.group_by("team").agg(pl.col("week").n_unique().alias("games"))
    ready = set(games_played.filter(pl.col("games") >= MIN_GAMES_CB - 1)["team"])
    latest = (
        injuries.filter((pl.col("season") == season) & (pl.col("week") <= current_week))
        .with_columns(name_column("full_name"))
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
