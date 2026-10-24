"""Load nflverse tables (stats, snaps, injuries, schedules, expected points) into raw parquet.

Only the columns later stages use are kept, cast to fixed dtypes. A missing or renamed column
fails here, loudly, not three stages later. Depth charts, weekly rosters, advanced stats, team pace
and FantasyPros rankings come from `ingest_role`.

Run: uv run python -m fantasy.stages.ingest_nfl [--force]
"""

import sys
import time
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import nflreadpy as nfl
import polars as pl

from fantasy import store
from fantasy.stages import ingest_role as role

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


# table name -> (loader, column that must not be null)
SOURCES: dict[str, tuple[Callable[[], pl.DataFrame], str | None]] = {
    "nfl_player_stats": (lambda: nfl.load_player_stats(role.seasons()), "player_id"),
    "nfl_team_stats": (lambda: nfl.load_team_stats(role.seasons()), None),
    "nfl_snaps": (
        lambda: with_gsis(nfl.load_snap_counts(role.seasons()), nfl.load_ff_playerids()),
        None,
    ),
    "nfl_injuries": (lambda: nfl.load_injuries(role.seasons()), "gsis_id"),
    "nfl_schedules": (lambda: nfl.load_schedules(role.seasons()), None),
    "nfl_ff_opportunity": (
        lambda: nfl.load_ff_opportunity(role.seasons(), stat_type="weekly"),
        "player_id",
    ),
    # role and context data for the learned model (see ingest_role)
    "nfl_rosters_weekly": (role.load_rosters, "gsis_id"),
    "nfl_depth": (role.load_depth, "gsis_id"),
    "nfl_advanced": (role.load_advanced, "gsis_id"),
    "nfl_team_pace": (role.load_pace, None),
    "nfl_ecr": (role.load_ecr, "gsis_id"),
}


def game_day_ended_since(gamedays: list[str], since: float, now: float) -> bool:
    """True if some game day finished (taken as the end of that UTC day) after `since`."""
    since_t, now_t = datetime.fromtimestamp(since, UTC), datetime.fromtimestamp(now, UTC)
    return any(
        since_t
        < datetime.combine(date.fromisoformat(g), datetime.min.time(), UTC) + timedelta(days=1)
        < now_t
        for g in gamedays
    )


def is_fresh(name: str, now: float | None = None) -> bool:
    """Newer than the TTL and no game day has ended since it was written."""
    path = store.table_path(name, "raw")
    now = time.time() if now is None else now
    if not path.exists() or now - path.stat().st_mtime >= TTL_SECONDS:
        return False
    schedule = store.table_path("nfl_schedules", "raw")
    if not schedule.exists():
        return False
    gamedays = pl.read_parquet(schedule, columns=["gameday"])["gameday"].drop_nulls().unique()
    return not game_day_ended_since(gamedays.to_list(), path.stat().st_mtime, now)


def latest_week(df: pl.DataFrame) -> tuple[int, int] | None:
    rows = df.select("season", "week").drop_nulls().sort("season", "week").tail(1).rows()
    return rows[0] if rows else None


def check_replacement(
    name: str, new: pl.DataFrame, required_id: str | None, data_dir: Path = store.DATA_DIR
) -> None:
    """Raise if `new` looks worse than the file it would replace: no rows, an older latest
    season and week, or a column that is entirely null now but was not before."""
    if new.height == 0:
        raise ValueError(f"{name}: the new table has no rows")
    if required_id and new[required_id].null_count() == new.height:
        raise ValueError(f"{name}: required column {required_id} is entirely null")
    path = store.table_path(name, "raw", data_dir)
    if not path.exists():
        return
    old = pl.read_parquet(path)
    if old.height == 0:
        return
    new_latest, old_latest = latest_week(new), latest_week(old)
    if new_latest and old_latest and new_latest < old_latest:
        raise ValueError(f"{name}: latest (season, week) {new_latest} is older than {old_latest}")
    emptied = [
        c
        for c in new.columns
        if new[c].null_count() == new.height
        and c in old.columns
        and old[c].null_count() < old.height
    ]
    if emptied:
        raise ValueError(f"{name}: columns now entirely null that had data before: {emptied}")


def run(force: bool = False) -> dict[str, str]:
    """Load every stale table, check it, and only then replace the files, so a failure part way
    leaves the whole raw set at the previous vintage."""
    report: dict[str, str] = {}
    loaded: dict[str, pl.DataFrame] = {}
    failures: dict[str, str] = {}
    for name, (load, required_id) in SOURCES.items():
        if not force and is_fresh(name):
            report[name] = "fresh, skipped"
            continue
        try:
            df = conform(name, load())
            if required_id:
                df = df.drop_nulls(required_id)
            check_replacement(name, df, required_id)
        except Exception as error:  # collected, then raised together below
            failures[name] = f"{type(error).__name__}: {error}"
            continue
        loaded[name] = df
    if failures:
        lines = "\n".join(f"  {n}: {m}" for n, m in failures.items())
        raise RuntimeError(
            "ingest_nfl failed; no raw table was replaced (all keep the previous vintage).\n"
            + lines
        )
    for name, df in loaded.items():
        store.write_table(name, df, area="raw")
        report[name] = f"{df.height} rows, latest {latest_week(df)}"
    return report


def main() -> None:
    for name, line in run(force="--force" in sys.argv).items():
        print(f"{name}: {line}")


if __name__ == "__main__":
    main()
