"""Load nflverse tables (stats, snaps, injuries, schedules, expected points) into raw parquet.

Only the columns later stages use are kept, cast to fixed dtypes. A missing or renamed column
fails here, loudly, not three stages later. Depth charts, weekly rosters, advanced stats, team pace
and FantasyPros rankings come from `ingest_role`.

Run: uv run python -m fantasy.stages.ingest_nfl [--force]
"""

import sys
import time
from collections.abc import Callable

import nflreadpy as nfl
import polars as pl

from fantasy import store
from fantasy.stages import ingest_role as role

SEASONS = list(range(2018, 2027))
TTL_SECONDS = 12 * 3600


def conform(name: str, df: pl.DataFrame) -> pl.DataFrame:
    """Select the registered columns in order and cast them. Raises if one is missing."""
    return df.select([pl.col(c).cast(t) for c, t in store.SCHEMAS[name].items()])


def with_gsis(snaps: pl.DataFrame, ffids: pl.DataFrame) -> pl.DataFrame:
    """Snap counts are keyed by PFR ID; add the nflverse (gsis) ID from the ID table."""
    ids = (
        ffids.select(pl.col("pfr_id").alias("pfr_player_id"), "gsis_id")
        .drop_nulls()
        .unique(subset="pfr_player_id")
    )
    return snaps.join(ids, on="pfr_player_id", how="left")


def drop_null_ids(df: pl.DataFrame, column: str) -> pl.DataFrame:
    return df.filter(pl.col(column).is_not_null())


# table name -> (loader, column that must not be null)
SOURCES: dict[str, tuple[Callable[[], pl.DataFrame], str | None]] = {
    "nfl_player_stats": (lambda: nfl.load_player_stats(SEASONS), "player_id"),
    "nfl_team_stats": (lambda: nfl.load_team_stats(SEASONS), None),
    "nfl_snaps": (lambda: with_gsis(nfl.load_snap_counts(SEASONS), nfl.load_ff_playerids()), None),
    "nfl_injuries": (lambda: nfl.load_injuries(SEASONS), "gsis_id"),
    "nfl_schedules": (lambda: nfl.load_schedules(SEASONS), None),
    "nfl_ff_opportunity": (
        lambda: nfl.load_ff_opportunity(SEASONS, stat_type="weekly"),
        "player_id",
    ),
    # role and context data for the learned model (see ingest_role)
    "nfl_rosters_weekly": (role.load_rosters, "gsis_id"),
    "nfl_depth": (role.load_depth, "gsis_id"),
    "nfl_advanced": (role.load_advanced, "gsis_id"),
    "nfl_team_pace": (role.load_pace, None),
    "nfl_ecr": (role.load_ecr, "gsis_id"),
}


def is_fresh(name: str, now: float | None = None) -> bool:
    path = store.table_path(name, "raw")
    now = time.time() if now is None else now
    return path.exists() and now - path.stat().st_mtime < TTL_SECONDS


def run(force: bool = False) -> dict[str, str]:
    report = {}
    for name, (load, required_id) in SOURCES.items():
        if not force and is_fresh(name):
            report[name] = "fresh, skipped"
            continue
        df = conform(name, load())
        if required_id:
            df = drop_null_ids(df, required_id)
        store.write_table(name, df, area="raw")
        latest = df.select("season", "week").drop_nulls().sort("season", "week").tail(1)
        report[name] = f"{df.height} rows, latest {latest.to_dicts()[0]}"
    return report


def main() -> None:
    for name, line in run(force="--force" in sys.argv).items():
        print(f"{name}: {line}")


if __name__ == "__main__":
    main()
