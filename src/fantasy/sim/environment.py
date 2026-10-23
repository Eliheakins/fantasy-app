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

import polars as pl

MIN_T = 2.0

Effects = dict[tuple[str, str], float]  # (position, kind) -> points


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
