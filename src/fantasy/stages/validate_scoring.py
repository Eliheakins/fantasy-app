"""Check computed points against Sleeper's reported player points for a completed week.

Run: uv run python -m fantasy.stages.validate_scoring [week]
Defenses are skipped (scored in E3-7). Unmapped players are counted, not compared.
"""

import json
import sys

import polars as pl

from fantasy import store
from fantasy.scoring import score_player_stats

TOLERANCE = 0.011


def compare_league(
    scoring: dict[str, float],
    sleeper_points: pl.DataFrame,
    id_map: pl.DataFrame,
    players: pl.DataFrame,
    stats: pl.DataFrame,
) -> pl.DataFrame:
    """sleeper_points: sleeper_id, points. Returns one row per compared player."""
    scored = score_player_stats(stats, scoring).select(
        pl.col("player_id").alias("gsis_id"), pl.col("points").alias("computed")
    )
    return (
        sleeper_points.join(players.select("sleeper_id", "full_name", "position"), on="sleeper_id")
        .filter(pl.col("position") != "DEF")
        .join(id_map.select("sleeper_id", "gsis_id"), on="sleeper_id")
        .filter(pl.col("gsis_id").is_not_null())
        .join(scored, on="gsis_id", how="left")
        .with_columns(pl.col("computed").fill_null(0.0))
        .with_columns((pl.col("computed") - pl.col("points")).alias("diff"))
    )


def run(week: int | None = None) -> None:
    leagues = store.read_table("leagues", "raw")
    week = week or int(leagues["current_week"][0]) - 1
    season = int(leagues["season"][0])
    players = store.read_table("sleeper_players", "raw")
    id_map = store.read_table("id_map")
    stats = (
        store.read_table("nfl_player_stats", "raw")
        .filter((pl.col("season") == season) & (pl.col("week") == week))
        .filter(pl.col("season_type") == "REG")
    )
    for row in leagues.iter_rows(named=True):
        sleeper_points = (
            store.read_table("matchup_players", "raw")
            .filter((pl.col("league_id") == row["league_id"]) & (pl.col("week") == week))
            .filter(pl.col("points").is_not_null())
            .select("sleeper_id", "points")
        )
        out = compare_league(
            json.loads(row["scoring_settings"]), sleeper_points, id_map, players, stats
        )
        bad = out.filter(pl.col("diff").abs() > TOLERANCE)
        print(f"{row['league_key']} week {week}: {out.height - bad.height} of {out.height} exact")
        for r in bad.sort("diff").iter_rows(named=True):
            who = f"{r['full_name']} ({r['position']})"
            print(f"  {who}: sleeper {r['points']}, ours {r['computed']}")


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else None)
