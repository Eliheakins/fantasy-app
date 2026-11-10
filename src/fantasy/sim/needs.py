"""Positional need and strength: what each team lacks, what it can spare, and how strong it is.

`TeamNeeds` drives the need-based trade finder (`trades`); `position_strength` is the Team page's
value over replacement by position.
"""

import polars as pl

from fantasy.sim.lineup import Player, auto_lineup
from fantasy.sim.odds import LeagueData
from fantasy.sim.roster import Valuer, ros_value, team_ids
from fantasy.sim.value import POSITIONS, season_value

NEED_MIN = 3.0  # rest-of-season points (about half a point a week) that count as a need filled
SURPLUS_COST = 1.0  # a player whose loss costs less than this (points) is surplus
PER_POSITION = 2  # best players per position in a candidate pool
SURPLUS_POOL = 3  # most valuable surplus bench players added to a candidate pool
BENCH_SPARES = 2  # benchmark starters kept per position, in case a team already holds the first


def benchmarks(data: LeagueData, valuer: Valuer) -> dict[str, list[str]]:
    """Per position, rostered players of typical starter quality (the last starter on an average
    team): the league's rank `teams x starting slots` by rest-of-season points, plus the next
    ones. Adding one to a roster measures how much a starter at that position would help."""
    ros = ros_value(data, data.rosters["gsis_id"].to_list())
    out: dict[str, list[str]] = {}
    for position in POSITIONS:
        ids = sorted(
            (i for i in ros if valuer.positions.get(i) == position), key=lambda i: (-ros[i], i)
        )
        rank = len(data.roster_ids) * max(valuer.slots.count(position), 1)
        start = max(min(rank, len(ids)) - 1, 0)
        out[position] = ids[start : start + BENCH_SPARES]
    return out


class TeamNeeds:
    """One team's positional need and surplus, from its own best weekly lineups.

    need[position]: expected points over the rest of the season that adding one typical starter at
    that position would give the team (FLEX and replacement stand-ins counted by the Valuer).
    cost(give): points lost by giving those players up; about 0 for a bench player behind a
    healthy starter. A swap's fit is the need it fills minus the cost of what it gives up."""

    def __init__(self, valuer: Valuer, ids: list[str], bench: dict[str, list[str]]) -> None:
        self.valuer, self.ids = valuer, list(ids)
        self.base = self._value(self.ids)
        self.bench = bench
        self._cost: dict[tuple[str, ...], float] = {}
        self._opened: dict[tuple[str, ...], float] = {}
        self._gain: dict[str, float] = {}
        self.need = {
            position: self.gain(next((b for b in spares if b not in self.ids), ""))
            for position, spares in bench.items()
        }

    def _value(self, ids: list[str]) -> float:
        """Best weekly lineups with free-agent stand-ins but no absence discount, so a spare
        behind a healthy starter is surplus rather than insurance."""
        v = self.valuer
        return season_value(v.slots, v.positions, v.values, ids, {}, v.replacements)

    def gain(self, player_id: str) -> float:
        """Points a single added player gives this team (0 for an empty id)."""
        if player_id and player_id not in self._gain:
            self._gain[player_id] = max(0.0, self._value([*self.ids, player_id]) - self.base)
        return self._gain.get(player_id, 0.0)

    def cost(self, give: tuple[str, ...]) -> float:
        key = tuple(sorted(give))
        if key not in self._cost:
            self._cost[key] = self.base - self._value([i for i in self.ids if i not in key])
        return self._cost[key]

    def opened(self, lost: tuple[str, ...]) -> float:
        """New need created by giving `lost` up: at each of their positions, how much more a
        typical starter would add to the team without them than with them."""
        key = tuple(sorted(lost))
        if key not in self._opened:
            rest = [i for i in self.ids if i not in key]
            base = self._value(rest)
            total = 0.0
            for position in {self.valuer.positions[i] for i in key}:
                spare = next((b for b in self.bench[position] if b not in rest), None)
                after = max(0.0, self._value([*rest, spare]) - base) if spare else 0.0
                total += max(0.0, after - self.need[position])
            self._opened[key] = total
        return self._opened[key]

    def fit(self, give: tuple[str, ...], get: tuple[str, ...]) -> tuple[float, list[str]]:
        """Need fit of a swap and the positions of need it fills: the need filled (what the best
        player received at a position of need adds, capped at that need) minus the need opened
        by what is given up. Positions that give and get equally cancel, so a like-for-like swap
        fits 0 however much better the player is."""
        at = self.valuer.positions
        net = {p: sum(at[g] == p for g in get) - sum(at[g] == p for g in give) for p in POSITIONS}
        filled = [p for p, n in net.items() if n > 0 and self.need[p] >= NEED_MIN]
        credit = sum(
            min(self.need[p], max(self.gain(g) for g in get if at[g] == p)) for p in filled
        )
        lost: list[str] = []
        for position in (p for p, n in net.items() if n < 0):
            of_position = sorted(
                (g for g in give if at[g] == position), key=lambda g: -self.cost((g,))
            )
            lost += of_position[: -net[position]]
        return credit - (self.opened(tuple(lost)) if lost else 0.0), filled

    def pool(self, ros: dict[str, float]) -> list[str]:
        """Candidates to trade away: the best players at each position plus the most valuable
        surplus bench players, who are the natural currency for a need swap."""
        at = self.valuer.positions
        live = sorted((i for i in self.ids if ros.get(i, 0.0) > 0), key=lambda i: (-ros[i], i))
        picked = [i for p in POSITIONS for i in [x for x in live if at[x] == p][:PER_POSITION]]
        surplus = [i for i in live if i not in picked and self.cost((i,)) < SURPLUS_COST]
        return picked + surplus[:SURPLUS_POOL]


def position_strength(data: LeagueData, valuer: Valuer | None = None) -> pl.DataFrame:
    """Each team's value over replacement by position: roster_id, position, vor_per_week, rank.

    For every remaining week a team's best lineup is scored against the replacement level at
    each starter's position (the best stand-in free agent that week); the average per week is
    summed by position. Rank 1 is the strongest team at that position."""
    valuer = valuer or Valuer(data)
    rows: list[tuple[int, str, float]] = []
    floor = {
        week: {p.position: p.value for p in reversed(valuer.replacements.get(week, []))}
        for week in valuer.values
    }
    for roster_id in data.roster_ids:
        ids = team_ids(data, roster_id)
        totals = dict.fromkeys(POSITIONS, 0.0)
        for week, values in valuer.values.items():
            pool = [
                Player(i, valuer.positions[i], values[i])
                for i in ids
                if i in values and i in valuer.positions
            ]
            for pid in auto_lineup(pool, valuer.slots).players:
                player = next(p for p in pool if p.id == pid)
                totals[player.position] += max(
                    0.0, player.value - floor[week].get(player.position, 0.0)
                )
        weeks = max(len(valuer.values), 1)
        rows += [(roster_id, pos, total / weeks) for pos, total in totals.items()]
    frame = pl.DataFrame(rows, schema=["roster_id", "position", "vor_per_week"], orient="row")
    return frame.with_columns(
        pl.col("vor_per_week")
        .rank("min", descending=True)
        .over("position")
        .cast(pl.Int64)
        .alias("rank")
    )
