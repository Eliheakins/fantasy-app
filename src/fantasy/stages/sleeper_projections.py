"""Archive Sleeper's weekly stat projections (RotoWire, served by an undocumented endpoint).

Past weeks on that endpoint are re-stamped after the games, so they cannot be trusted for a
backtest. Snapshotting before games builds a clean history to test them against. Nothing
downstream reads the archive yet.

Run: uv run python -m fantasy.stages.sleeper_projections
"""

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl

from fantasy import store
from fantasy.config import load_config

URL = "https://api.sleeper.com/projections/nfl/{season}/{week}"
POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]
WEEKS_AHEAD = 4
LAST_WEEK = 18
PAUSE_SECONDS = 0.3


def snapshot_frame(week: int, fetched_at: str, items: list[dict[str, Any]]) -> pl.DataFrame:
    rows = [
        {
            "fetched_at": fetched_at,
            "week": week,
            "sleeper_id": str(d["player_id"]),
            "stats": json.dumps(d["stats"], sort_keys=True),
        }
        for d in items
        if d.get("stats")
    ]
    return pl.DataFrame(rows, schema=store.SCHEMAS["sleeper_proj_snapshots"])


def score_stats(stats: dict[str, float], scoring: dict[str, float]) -> float:
    """A projected stat line under a league's scoring. Sleeper projects kickers' long field
    goals and misses in coarser buckets than leagues score them, so those are mapped across."""
    total = sum(
        value * scoring.get(key, 0.0)
        for key, value in stats.items()
        if not key.startswith("fgmiss_")
    )
    if "fgm_50p" in stats and not scoring.get("fgm_50p"):
        total += stats["fgm_50p"] * scoring.get(
            "fgm_50_59", 0.0
        )  # shortcut: 60+ counted as 50 to 59
    for key, value in stats.items():
        if key.startswith("fgmiss_"):
            specific = scoring.get(key) or scoring.get(
                "fgmiss_50_59" if key == "fgmiss_50p" else ""
            )
            total += value * (specific or scoring.get("fgmiss", 0.0))
    return total


def scored_latest(snapshots: pl.DataFrame, scoring: dict[str, float]) -> pl.DataFrame:
    """Latest snapshot per week, scored: sleeper_id, week, projection."""
    latest = snapshots.filter(pl.col("fetched_at") == pl.col("fetched_at").max().over("week"))
    scores = [score_stats(json.loads(s), scoring) for s in latest["stats"]]
    return latest.select("sleeper_id", "week").with_columns(
        pl.Series("projection", scores, dtype=pl.Float64)
    )


def run(data_dir: Path = store.DATA_DIR) -> int:
    season = load_config().season
    current = int(store.read_table("leagues", "raw", data_dir)["current_week"].to_numpy().max())
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    frames = []
    for week in range(current, min(current + WEEKS_AHEAD, LAST_WEEK + 1)):
        resp = httpx.get(
            URL.format(season=season, week=week),
            params={"season_type": "regular", "position[]": POSITIONS},
            timeout=60,
        )
        resp.raise_for_status()
        frames.append(snapshot_frame(week, fetched_at, resp.json()))
        time.sleep(PAUSE_SECONDS)
    new = pl.concat(frames)
    try:
        new = pl.concat([store.read_table("sleeper_proj_snapshots", "archive", data_dir), new])
    except FileNotFoundError:
        pass
    store.write_table("sleeper_proj_snapshots", new, "archive", data_dir)
    leagues = store.read_table("leagues", "raw", data_dir)
    scored = [
        scored_latest(new, json.loads(lg["scoring_settings"])).with_columns(
            pl.lit(lg["league_id"]).alias("league_id")
        )
        for lg in leagues.iter_rows(named=True)
    ]
    out = pl.concat(scored).select(*store.SCHEMAS["proj_sleeper"])
    store.write_table("proj_sleeper", out, "derived", data_dir)
    return new.height


if __name__ == "__main__":
    print(f"{run()} rows in the archive")
