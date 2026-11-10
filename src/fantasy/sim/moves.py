"""Roster moves: free agents, ranking adds, and applying and evaluating a trade.

A facade over the modules that hold the logic, so callers keep writing `moves.<name>`:
`roster` (who is on a team, who is free, `Valuer`), `waivers`, `trades` (apply, evaluate and
search), `trade_labels` (how a found trade is labelled, ranked and de-duplicated) and `needs`
(positional need and strength). New code in this package imports from those modules directly.
"""

from fantasy.sim.needs import NEED_MIN, TeamNeeds, benchmarks, position_strength
from fantasy.sim.roster import (
    Valuer,
    free_agents,
    position_of,
    ros_value,
    rostered,
    team_ids,
    team_total,
    week_values,
    with_roster,
)
from fantasy.sim.trade_labels import (
    FINDER_COLUMNS,
    ODDS_TOL,
    drop_addons,
    rank_key,
    swap_kind,
)
from fantasy.sim.trades import (
    SIZES,
    apply_trade,
    evaluate_trade,
    find_trades,
    paired_se,
    trade_pool,
)
from fantasy.sim.waivers import Waiver, best_swap, waiver_candidates, waiver_odds

__all__ = [
    "FINDER_COLUMNS",
    "NEED_MIN",
    "ODDS_TOL",
    "SIZES",
    "TeamNeeds",
    "Valuer",
    "Waiver",
    "apply_trade",
    "benchmarks",
    "best_swap",
    "drop_addons",
    "evaluate_trade",
    "find_trades",
    "free_agents",
    "paired_se",
    "position_of",
    "position_strength",
    "rank_key",
    "ros_value",
    "rostered",
    "swap_kind",
    "team_ids",
    "team_total",
    "trade_pool",
    "waiver_candidates",
    "waiver_odds",
    "week_values",
    "with_roster",
]
