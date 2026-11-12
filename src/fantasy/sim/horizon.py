"""Which weeks a move is valued over: the rest of the season, or the playoff weeks."""

from typing import Literal

from fantasy.sim.odds import LeagueData

Horizon = Literal["ros", "playoffs"]


def horizon_weeks(data: LeagueData, horizon: Horizon) -> tuple[int, ...]:
    """Weeks still to come for `horizon`. "ros" is every projected week from the current one;
    "playoffs" is `playoff_start` through the bracket's last week (from its size and round type),
    cut to weeks not yet played, so empty after the final."""
    if horizon == "ros":
        weeks = set(data.projections["week"].to_list())
        return tuple(sorted(w for w in weeks if w >= data.current_week))
    last = data.playoff_start + data.playoff_weeks - 1
    return tuple(range(max(data.playoff_start, data.current_week), last + 1))
