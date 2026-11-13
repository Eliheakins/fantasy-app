"""Shared roster helpers for roster moves: who is on a team, who is free, and `Valuer`.

Everything here works on one league's LeagueData. Players are skill players (QB, RB, WR, TE) with
projections; each team's K and DEF are its own projections (`LeagueData.kd_slot`), which a move
leaves unchanged. `waivers`, `trades` and `needs` build on these; `moves` re-exports all of them.
"""

from collections.abc import Collection

import polars as pl

from fantasy.sim.lineup import auto_lineup, lineup_slots, week_pool
from fantasy.sim.odds import HAZARD, STAY_OUT, LeagueData
from fantasy.sim.value import (
    absence_probs,
    conditional_values,
    play_curves,
    replacement_pool,
    season_value,
    values_by_week,
)


def position_of(data: LeagueData) -> dict[str, str]:
    on_rosters = dict(zip(data.rosters["gsis_id"], data.rosters["position"], strict=True))
    return {**data.positions, **on_rosters}


def week_values(data: LeagueData) -> dict[int, dict[str, float]]:
    return values_by_week(data.projections)


def ros_value(
    data: LeagueData, ids: list[str], weeks: Collection[int] | None = None
) -> dict[str, float]:
    """Projected points over the rest of the season (or only `weeks`), per player."""
    wanted = data.projections.filter(pl.col("gsis_id").is_in(ids))
    if weeks is not None:
        wanted = wanted.filter(pl.col("week").is_in(list(weeks)))
    sums = dict(wanted.group_by("gsis_id").agg(pl.col("projection").sum()).iter_rows())
    return {i: float(sums.get(i, 0.0)) for i in ids}


def with_roster(data: LeagueData, roster_id: int, ids: list[str]) -> pl.DataFrame:
    """The league's rosters with `roster_id`'s players replaced by `ids`."""
    rest = data.rosters.filter(pl.col("roster_id") != roster_id)
    positions = position_of(data)
    rows = [(roster_id, i, positions[i]) for i in ids]
    return pl.concat([rest, pl.DataFrame(rows, schema=rest.schema, orient="row")])


def rostered(data: LeagueData, rosters: pl.DataFrame | None = None) -> set[str]:
    return set((data.rosters if rosters is None else rosters)["gsis_id"].to_list())


def free_agents(data: LeagueData, rosters: pl.DataFrame | None = None) -> list[str]:
    """Active players Sleeper lists (data.positions) with a projection and no team in the league."""
    available = set(data.projections["gsis_id"].to_list()) & set(data.positions)
    return sorted(available - rostered(data, rosters))


def team_total(
    data: LeagueData,
    ids: list[str],
    values_by_week: dict[int, dict[str, float]] | None = None,
    slots: list[str] | None = None,
    positions: dict[str, str] | None = None,
) -> float:
    """Expected skill-position points over the rest of the season with best weekly lineups.

    Pass `values_by_week` (from week_values), `slots` and `positions` when scoring many rosters
    to skip recomputing them."""
    slots = lineup_slots(data.roster_positions) if slots is None else slots
    positions = position_of(data) if positions is None else positions
    total = 0.0
    for values in (week_values(data) if values_by_week is None else values_by_week).values():
        total += auto_lineup(week_pool(ids, positions, values), slots).total
    return total


def team_ids(data: LeagueData, roster_id: int, rosters: pl.DataFrame | None = None) -> list[str]:
    frame = data.rosters if rosters is None else rosters
    return frame.filter(pl.col("roster_id") == roster_id)["gsis_id"].to_list()


class Valuer:
    """Expected points over the rest of the season for a set of players, counting absences and
    free-agent stand-ins (see sim/value.py). Build once per league and reuse."""

    def __init__(self, data: LeagueData, weeks: Collection[int] | None = None) -> None:
        """`weeks` limits the sum to those weeks; absence chances are still built from every
        projected week, so a kept week keeps its true offset from the current week."""
        self.data = data
        self.weeks = weeks
        self.slots = lineup_slots(data.roster_positions)
        self.positions = position_of(data)
        # points when playing, by week; absences are weighed separately
        self.values = conditional_values(data.projections)
        n = len(self.values)
        curves = play_curves(data.projections, sorted(self.values))
        self.absence = {
            g: absence_probs(curves.get(g, (1.0,)), n, HAZARD, STAY_OUT) for g in self.positions
        }
        self.replacements = replacement_pool(free_agents(data), self.positions, self.values)

    def __call__(self, ids: list[str]) -> float:
        return season_value(
            self.slots,
            self.positions,
            self.values,
            ids,
            self.absence,
            self.replacements,
            self.weeks,
        )
