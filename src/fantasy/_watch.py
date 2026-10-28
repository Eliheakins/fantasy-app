"""Drop-risk watch: my players whose snap share or market value is falling, or who are flagged."""

from pathlib import Path

import polars as pl

from fantasy._engine import _injury_note, _league, _names, _read
from fantasy._values import market_values
from fantasy.config import load_config
from fantasy.sim import moves
from fantasy.sim.watch import market_drop, role_drop

TOP_N = 8


def watchlist(league_key: str, data_dir: Path) -> pl.DataFrame:
    """My flagged players, most rest-of-season points first. Columns: gsis_id, full_name,
    position, ros_points and reasons (one sentence for each fact that put him on the list)."""
    data, mine = _league(league_key)
    ids = moves.team_ids(data, mine)
    ros, names, positions = moves.ros_value(data, ids), _names(), moves.position_of(data)
    snaps = (
        _read("nfl_snaps", data_dir, "raw")
        .filter(
            (pl.col("season") == load_config().season)
            & (pl.col("week") < data.current_week)
            & pl.col("gsis_id").is_in(ids)
            & (pl.col("offense_snaps") > 0)
        )
        .sort("week")
    )
    shares = {g: s["offense_pct"].to_list() for (g,), s in snaps.group_by("gsis_id")}
    market = {
        r["gsis_id"]: r for r in market_values(league_key, ids, data_dir).iter_rows(named=True)
    }
    rows = []
    for gsis_id in sorted(ids, key=lambda i: (-ros[i], i)):
        reasons = []
        if (role := role_drop(shares.get(gsis_id, []))) is not None:
            reasons.append(f"snap share {role[0]:.0%} before, {role[1]:.0%} in the last 3 games")
        row = market.get(gsis_id)
        if row is not None and (fall := market_drop(row["value"], row["trend_30_day"])) is not None:
            reasons.append(f"market value down {fall:.0%} in 30 days")
        if (note := _injury_note(data, gsis_id)) is not None:
            reasons.append(note)
        if reasons:
            rows.append(
                (gsis_id, names.get(gsis_id, gsis_id), positions[gsis_id], ros[gsis_id], reasons)
            )
    schema: dict[str, pl.DataType | type[pl.DataType]] = {
        "gsis_id": pl.String, "full_name": pl.String, "position": pl.String,
        "ros_points": pl.Float64, "reasons": pl.List(pl.String),
    }  # fmt: skip
    return pl.DataFrame(rows[:TOP_N], schema=schema, orient="row")
