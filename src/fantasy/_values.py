"""Market values (FantasyCalc) for one league, keyed by nflverse id."""

from pathlib import Path
from typing import Any

import polars as pl

from fantasy import store
from fantasy._engine import _id_map, _read
from fantasy.sim.setting import setting_for
from fantasy.sim.value import accepted_share, market_hint

COLUMNS = ["gsis_id", "value", "overall_rank", "position_rank", "trend_30_day", "fetched_at"]


def _format_key(league_key: str, data_dir: Path | None) -> str:
    league = _read("leagues", data_dir).filter(pl.col("league_key") == league_key)
    if league.is_empty():
        raise ValueError(f"unknown league {league_key!r}")
    row = league.row(0, named=True)
    return setting_for(row["scoring_settings"], row["roster_positions"], row["num_teams"]).key


def market_history(league_key: str, gsis_id: str, data_dir: Path | None) -> list[dict[str, Any]]:
    """One value per day (the day's latest fetch) for the league's format, oldest first; empty
    when the archive table or the player is missing."""
    key = _format_key(league_key, data_dir)
    ids = _id_map(data_dir).filter(pl.col("gsis_id") == gsis_id)["sleeper_id"]
    found = _read("market_values_history", data_dir, "archive").filter(
        (pl.col("format") == key) & pl.col("sleeper_id").is_in(ids.implode())
    )
    return (
        found.sort("fetched_at")
        .with_columns(day=pl.col("fetched_at").str.slice(0, 10))
        .group_by("day", maintain_order=True)
        .last()
        .select("day", "value")
        .to_dicts()
    )


def market_values(league_key: str, gsis_ids: list[str], data_dir: Path | None) -> pl.DataFrame:
    """Values for the given players under the league's setting; empty when the table is missing."""
    empty = pl.DataFrame(
        schema={c: store.SCHEMAS["market_values"].get(c, pl.String) for c in COLUMNS}
    )
    key = _format_key(league_key, data_dir)
    values = _read("market_values", data_dir, "raw").filter(pl.col("format") == key)
    if values.is_empty():
        return empty
    return (
        values.join(_id_map(data_dir), on="sleeper_id")
        .filter(pl.col("gsis_id").is_in(gsis_ids))
        .select(COLUMNS)
        .sort("overall_rank")
    )


def past_trade_ratios(data_dir: Path | None) -> list[float]:
    """Market value received over value given, for each side of every completed trade in the
    leagues, at today's values (the old values are not kept). Sides with an unvalued player or
    a zero total are left out. Draft picks are not in the table, so a side that traded picks
    looks smaller than it was."""
    trades = _read("transactions", data_dir, "raw").filter(
        (pl.col("type") == "trade") & (pl.col("status") == "complete")
    )
    values = _read("market_values", data_dir, "raw")
    if trades.is_empty() or values.is_empty():
        return []
    ratios: list[float] = []
    for league in _read("leagues", data_dir).iter_rows(named=True):
        key = setting_for(
            league["scoring_settings"], league["roster_positions"], league["num_teams"]
        ).key
        value = dict(
            values.filter(pl.col("format") == key).select("sleeper_id", "value").iter_rows()
        )
        mine = trades.filter(pl.col("league_id") == league["league_id"])
        for (_, _), side in mine.group_by("transaction_id", "roster_id"):
            got = side.filter(pl.col("action") == "add")["sleeper_id"].to_list()
            gave = side.filter(pl.col("action") == "drop")["sleeper_id"].to_list()
            if not got or not gave or any(i not in value for i in got + gave):
                continue
            total_gave = sum(value[i] for i in gave)
            if total_gave > 0:
                ratios.append(sum(value[i] for i in got) / total_gave)
    return ratios


def trade_market(
    league_key: str, trades: list[tuple[list[str], list[str]]], data_dir: Path | None
) -> list[dict[str, Any] | None]:
    """Per (give_ids, get_ids): summed market value of each side, the hint and the values' date.
    None for every trade when there are no values; a player without one counts as missing."""
    wanted = sorted({i for give, get in trades for i in (*give, *get)})
    found = market_values(league_key, wanted, data_dir)
    if found.is_empty():
        return [None] * len(trades)
    past = past_trade_ratios(data_dir)
    value = dict(zip(found["gsis_id"], found["value"], strict=True))
    fetched = dict(zip(found["gsis_id"], found["fetched_at"], strict=True))
    out: list[dict[str, Any] | None] = []
    for give, get in trades:
        give_value = sum(value.get(i, 0.0) for i in give)
        get_value = sum(value.get(i, 0.0) for i in get)
        missing = sum(i not in value for i in (*give, *get))
        dates = [fetched[i] for i in (*give, *get) if i in fetched]
        # the partner receives my give and sends my get
        priced = not missing and give_value > 0 and get_value > 0
        share = accepted_share(give_value / get_value, past) if priced else None
        out.append(
            {
                "give_value": give_value, "get_value": get_value,
                "accepted_share": share, "accepted_sides": len(past),
                "hint": market_hint(give_value, get_value, missing),
                "fetched_at": max(dates) if dates else max(found["fetched_at"]),
            }
        )  # fmt: skip
    return out
