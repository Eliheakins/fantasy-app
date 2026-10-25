"""Market values (FantasyCalc) for one league, keyed by nflverse id."""

from pathlib import Path

import polars as pl

from fantasy import store
from fantasy._engine import _id_map, _read
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
