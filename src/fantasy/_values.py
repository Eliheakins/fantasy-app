"""Market values (FantasyCalc) for one league, keyed by nflverse id."""

from pathlib import Path
from typing import Any

import polars as pl

from fantasy import store
from fantasy._engine import _id_map, _read
from fantasy.sim.value import market_hint
from fantasy.stages.market_values import setting_for

COLUMNS = ["gsis_id", "value", "overall_rank", "position_rank", "trend_30_day", "fetched_at"]


def market_values(league_key: str, gsis_ids: list[str], data_dir: Path) -> pl.DataFrame:
    """Values for the given players under the league's setting; empty when the table is missing."""
    empty = pl.DataFrame(
        schema={c: store.SCHEMAS["market_values"].get(c, pl.String) for c in COLUMNS}
    )
    league = _read("leagues", data_dir).filter(pl.col("league_key") == league_key)
    if league.is_empty():
        raise ValueError(f"unknown league {league_key!r}")
    row = league.row(0, named=True)
    key = setting_for(row["scoring_settings"], row["roster_positions"], row["num_teams"]).key
    values = _read("market_values", data_dir, "raw").filter(pl.col("format") == key)
    if values.is_empty():
        return empty
    return (
        values.join(_id_map(), on="sleeper_id")
        .filter(pl.col("gsis_id").is_in(gsis_ids))
        .select(COLUMNS)
        .sort("overall_rank")
    )


def trade_market(
    league_key: str, trades: list[tuple[list[str], list[str]]], data_dir: Path
) -> list[dict[str, Any] | None]:
    """Per (give_ids, get_ids): summed market value of each side, the hint and the values' date.
    None for every trade when there are no values; a player without one counts as missing."""
    wanted = sorted({i for give, get in trades for i in (*give, *get)})
    found = market_values(league_key, wanted, data_dir)
    if found.is_empty():
        return [None] * len(trades)
    value = dict(zip(found["gsis_id"], found["value"], strict=True))
    fetched = dict(zip(found["gsis_id"], found["fetched_at"], strict=True))
    out: list[dict[str, Any] | None] = []
    for give, get in trades:
        give_value = sum(value.get(i, 0.0) for i in give)
        get_value = sum(value.get(i, 0.0) for i in get)
        missing = sum(i not in value for i in (*give, *get))
        dates = [fetched[i] for i in (*give, *get) if i in fetched]
        out.append(
            {
                "give_value": give_value, "get_value": get_value,
                "hint": market_hint(give_value, get_value, missing),
                "fetched_at": max(dates) if dates else max(found["fetched_at"]),
            }
        )  # fmt: skip
    return out
