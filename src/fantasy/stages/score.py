"""Score every player-week under each league's rules and attach game context.

Writes team_games (one row per team per game, with spread-implied totals) and player_points
(league-scored points for 2018 onward, with the game's context columns).

Run: uv run python -m fantasy.stages.score
"""

import json

import polars as pl

from fantasy import store
from fantasy.scoring import score_player_stats

SKILL_POSITIONS = ["QB", "RB", "WR", "TE", "K"]
CONTEXT = ["is_home", "team_implied", "opp_implied", "total_line", "roof", "temp", "wind"]


def team_games_frame(schedules: pl.DataFrame) -> pl.DataFrame:
    """Two rows per game. spread is from the team's view (positive means favored)."""
    shared = ["game_id", "season", "week", "game_type", "gameday"]
    shared += ["total_line", "roof", "temp", "wind"]
    home = schedules.select(
        *shared,
        team=pl.col("home_team"),
        opponent=pl.col("away_team"),
        is_home=pl.lit(True),
        spread=pl.col("spread_line"),
        rest=pl.col("home_rest"),
        points_for=pl.col("home_score"),
        points_against=pl.col("away_score"),
    )
    away = schedules.select(
        *shared,
        team=pl.col("away_team"),
        opponent=pl.col("home_team"),
        is_home=pl.lit(False),
        spread=-pl.col("spread_line"),
        rest=pl.col("away_rest"),
        points_for=pl.col("away_score"),
        points_against=pl.col("home_score"),
    )
    return pl.concat([home, away]).with_columns(
        team_implied=(pl.col("total_line") + pl.col("spread")) / 2,
        opp_implied=(pl.col("total_line") - pl.col("spread")) / 2,
    )


def player_points_frame(
    stats: pl.DataFrame, team_games: pl.DataFrame, scoring: dict[str, float], league_id: str
) -> pl.DataFrame:
    scored = score_player_stats(stats.filter(pl.col("position").is_in(SKILL_POSITIONS)), scoring)
    context = team_games.select("season", "week", "team", *CONTEXT)
    return (
        scored.join(context, on=["season", "week", "team"], how="left")
        .with_columns(pl.col("player_id").alias("gsis_id"), pl.lit(league_id).alias("league_id"))
        .select(*store.SCHEMAS["player_points"])
    )


def run() -> dict[str, int]:
    games = team_games_frame(store.read_table("nfl_schedules", "raw")).select(
        *store.SCHEMAS["team_games"]
    )
    stats = store.read_table("nfl_player_stats", "raw")
    frames = [
        player_points_frame(stats, games, json.loads(r["scoring_settings"]), r["league_id"])
        for r in store.read_table("leagues", "raw").iter_rows(named=True)
    ]
    points = pl.concat(frames)
    store.write_tables({"team_games": games, "player_points": points})
    return {"team_games": games.height, "player_points": points.height}


def main() -> None:
    for name, rows in run().items():
        print(f"{name}: {rows} rows")


if __name__ == "__main__":
    main()
