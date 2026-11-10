"""Advance each league's `current_week` once every game of that week has a score.

Sleeper's `leg` only moves on Wednesday, so on Tuesday every screen would still show the finished
week. Runs after `ingest_nfl` (the scores) and before the stages that read `current_week`.

Run: uv run python -m fantasy.stages.week_rollover
"""

from pathlib import Path

import polars as pl

from fantasy import store
from fantasy.config import load_config

LAST_WEEK = 18


def week_is_final(schedules: pl.DataFrame, season: int, week: int) -> bool:
    """True when the week has games and every one has both scores."""
    games = schedules.filter((pl.col("season") == season) & (pl.col("week") == week))
    if games.is_empty():
        return False
    return games.select(pl.col("home_score").is_not_null() & pl.col("away_score").is_not_null())[
        "home_score"
    ].all()


def advance_finished_week(
    leagues: pl.DataFrame, schedules: pl.DataFrame, season: int
) -> pl.DataFrame:
    """`leagues` with `current_week` moved up one where that week is final, up to LAST_WEEK."""
    advanced = [
        min(week + 1, LAST_WEEK)
        if week is not None and week_is_final(schedules, season, week)
        else week
        for week in leagues["current_week"]
    ]
    return leagues.with_columns(
        pl.Series("current_week", advanced, dtype=leagues["current_week"].dtype)
    )


def run(data_dir: Path | None = None) -> int:
    """Rewrite the leagues table; returns how many leagues moved to a later week."""
    leagues = store.read_table("leagues", "raw", data_dir)
    schedules = store.read_table("nfl_schedules", "raw", data_dir)
    moved = advance_finished_week(leagues, schedules, load_config().season)
    store.write_table("leagues", moved, "raw", data_dir)
    return int((moved["current_week"] != leagues["current_week"]).sum())


def main() -> None:
    print(f"leagues moved to the next week: {run()}")


if __name__ == "__main__":
    main()
