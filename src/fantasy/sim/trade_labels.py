"""Labelling, ranking and de-duplicating the trades `find_trades` simulates."""

from typing import Any

import polars as pl

from fantasy.sim.needs import NEED_MIN

# A need swap may cost either side up to one percentage point of (playoff + title) odds. Chosen
# as about twice the paired Monte Carlo error of a single odds change at 20,000 sims (0.3 to
# 0.5 points on real data), so a swap is not rejected for noise alone, yet a visible loss is.
ODDS_TOL = 0.01
FINDER_COLUMNS: dict[str, pl.DataType | type[pl.DataType]] = {
    "partner_id": pl.Int64,
    "give_ids": pl.List(pl.String),
    "get_ids": pl.List(pl.String),
    "my_playoff": pl.Float64,
    "my_title": pl.Float64,
    "their_playoff": pl.Float64,
    "their_title": pl.Float64,
    "se_title": pl.Float64,
    "kind": pl.String,
    "my_fit": pl.Float64,
    "their_fit": pl.Float64,
    "my_needs": pl.List(pl.String),
    "their_needs": pl.List(pl.String),
}


def swap_kind(result: dict[str, float], my_fit: float, their_fit: float) -> str | None:
    """ "win-win" if both teams' odds rise, "need swap" if neither loses more than ODDS_TOL and
    both fill a need (fit of at least NEED_MIN), else None (rejected)."""
    if _both_gain(result):
        return "win-win"
    mine = result["my_playoff"] + result["my_title"]
    theirs = result["their_playoff"] + result["their_title"]
    if min(mine, theirs) >= -ODDS_TOL and min(my_fit, their_fit) >= NEED_MIN:
        return "need swap"
    return None


def rank_key(row: dict[str, Any]) -> tuple[float, float, float]:
    """Need fit first (the weaker side's; below NEED_MIN it counts as none, a negative one as is),
    then my title and playoff odds change."""
    weaker = min(row["my_fit"], row["their_fit"])
    return (
        -(weaker if weaker >= NEED_MIN else min(weaker, 0.0)),
        -row["my_title"],
        -row["my_playoff"],
    )


def _both_gain(result: dict[str, float]) -> bool:
    """Both teams' playoff plus title odds rise. Neither alone works: a team near the playoff
    ceiling can only gain title odds, and title odds alone are too noisy."""
    return (
        result["my_playoff"] + result["my_title"] > 0
        and result["their_playoff"] + result["their_title"] > 0
    )


def _is_addon(big: dict[str, Any], small: dict[str, Any], positions: dict[str, str]) -> bool:
    """`big` is `small` plus one like-for-like leg (same position each way) that moves my
    playoff plus title odds by less than ODDS_TOL."""
    if big["partner_id"] != small["partner_id"]:
        return False
    extra_give = set(big["give_ids"]) - set(small["give_ids"])
    extra_get = set(big["get_ids"]) - set(small["get_ids"])
    give_subset = set(small["give_ids"]) < set(big["give_ids"])
    if not (give_subset and set(small["get_ids"]) < set(big["get_ids"])):
        return False
    if len(extra_give) != 1 or len(extra_get) != 1:
        return False
    if positions[next(iter(extra_give))] != positions[next(iter(extra_get))]:
        return False

    def odds(r: dict[str, Any]) -> float:
        return float(r["my_playoff"] + r["my_title"])

    return abs(odds(big) - odds(small)) < ODDS_TOL


def drop_addons(rows: list[dict[str, Any]], positions: dict[str, str]) -> list[dict[str, Any]]:
    """Rows without the ones that are a smaller listed swap plus a like-for-like add-on leg."""
    return [r for r in rows if not any(_is_addon(r, s, positions) for s in rows)]
