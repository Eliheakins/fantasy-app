"""The archive of each refresh's projections for the next game (`proj_snapshots`)."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import polars as pl

from fantasy import store
from fantasy._runs import note_soft_failure
from fantasy.stages.project import GROUP


def snapshot_frame(
    learned: pl.DataFrame, baseline: pl.DataFrame, fetched_at: str, current_week: int
) -> pl.DataFrame:
    """The next game's projection from both models, as made at `fetched_at`."""
    keys = [*GROUP, "season", "week"]
    now = learned.filter(pl.col("is_future") & (pl.col("week") == current_week)).select(
        *keys, pl.col("projection").alias("learned")
    )
    base = baseline.filter(pl.col("is_future") & (pl.col("week") == current_week)).select(
        *keys, pl.col("projection").alias("baseline")
    )
    return (
        now.join(base, on=keys, how="left")
        .with_columns(pl.lit(fetched_at).alias("fetched_at"))
        .select(*GROUP, "season", "week", "fetched_at", "learned", "baseline")
    )


def unplayed(final: pl.DataFrame, games: pl.DataFrame, today: str) -> pl.DataFrame:
    """Rows of `final` whose game has no score yet and is not dated before `today` (YYYY-MM-DD).
    The archive cannot be regenerated, so a game already played or started is never snapshotted:
    its projection would have seen the result or been made after kickoff."""
    open_games = games.filter(pl.col("points_for").is_null() & (pl.col("gameday") >= today)).select(
        "season", "week", "team"
    )
    return final.join(open_games, on=["season", "week", "team"], how="semi")


def archive_snapshot(final: pl.DataFrame, current_week: int, games: pl.DataFrame) -> None:
    """Append this refresh's projections for the next game to the archive. Scored after the games,
    they are the one clean test of the learned model: nothing was chosen with them in view."""
    now = datetime.now(UTC)
    fetched_at = now.isoformat(timespec="seconds")
    # gamedays are US dates, so compare with the Eastern date: after 8pm ET the UTC date has rolled
    # over while a night game is still open
    eastern_today = now.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    eligible = unplayed(final, games, eastern_today)
    next_rows = final.filter(pl.col("is_future") & (pl.col("week") == current_week)).height
    if eligible.filter(pl.col("is_future") & (pl.col("week") == current_week)).height < next_rows:
        print("learn: WARNING some next games are played or past kickoff; not archived")
    new = snapshot_frame(eligible, store.read_table("proj_baseline"), fetched_at, current_week)
    if new.is_empty():
        print(f"learn: WARNING no unplayed week {current_week} games; archive left unchanged")
        return
    missing = int(new["baseline"].is_null().sum())
    if missing:
        print(f"learn: WARNING {missing} archived rows have no baseline projection")
        note_soft_failure(f"{missing} archived rows have no baseline projection")  # kept: no redo
    new = new.select(*store.SCHEMAS["proj_snapshots"])
    store.write_table("proj_snapshots", store.with_archive("proj_snapshots", new), "archive")
