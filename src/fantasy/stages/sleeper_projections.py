"""Archive Sleeper's weekly stat projections (RotoWire, served by an undocumented endpoint).

Past weeks on that endpoint are re-stamped after the games, so they cannot be trusted for a
backtest. Snapshotting before games builds a clean history to test them against. Nothing
downstream reads the archive yet.

Run: uv run python -m fantasy.stages.sleeper_projections
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from fantasy import store
from fantasy.config import load_config
from fantasy.sources.sleeper import fetch

PROJECTIONS_BASE = "https://api.sleeper.com"
POSITIONS = ["QB", "RB", "WR", "TE", "K", "DEF"]
WEEKS_AHEAD = 4
LAST_WEEK = 18
# Sleeper stat keys no league scores: projection totals, ADP and volume stats
IGNORED_KEYS = {
    "adp_dd_ppr", "cmp_pct", "def_fum_td", "def_kr_td", "def_pr_td", "fga", "gp",
    "pos_adp_dd_ppr", "pr", "pr_td", "pts_half_ppr", "pts_idp", "pts_ppr", "pts_std",
    "rec_tgt", "xpa",
}  # fmt: skip


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


def unknown_keys(snapshots: pl.DataFrame, scoring: dict[str, float]) -> list[str]:
    """Projected stat keys that neither the league scoring lists nor IGNORED_KEYS covers."""
    seen = {key for s in snapshots["stats"].unique() for key in json.loads(s)}
    return sorted(seen - scoring.keys() - IGNORED_KEYS)


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
    unknown = unknown_keys(latest, scoring)
    if unknown:  # these are scored as zero
        print(f"warning: Sleeper projection keys not in the league scoring: {unknown}")
    scores = [score_stats(json.loads(s), scoring) for s in latest["stats"]]
    return latest.select("sleeper_id", "week").with_columns(
        pl.Series("projection", scores, dtype=pl.Float64)
    )


def fetch_week(season: int, week: int) -> list[dict[str, Any]]:
    items = fetch(
        f"/projections/nfl/{season}/{week}",
        {"season_type": "regular", "position[]": POSITIONS},
        base=PROJECTIONS_BASE,
    )
    if not isinstance(items, list):
        raise RuntimeError(
            f"Sleeper projections for week {week} came back as {type(items).__name__}"
        )
    return items


def run(data_dir: Path = store.DATA_DIR) -> int:
    season = load_config().season
    leagues = store.read_table("leagues", "raw", data_dir)
    current = int(leagues["current_week"].to_numpy().max())
    weeks = range(current, min(current + WEEKS_AHEAD, LAST_WEEK + 1))
    if not weeks:
        print(f"week {current} is past the last projected week; nothing to snapshot")
        return 0
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
    frames = [snapshot_frame(w, fetched_at, fetch_week(season, w)) for w in weeks]
    if frames[0].height == 0:  # latest-per-week scoring would silently reuse an old snapshot
        raise RuntimeError(f"Sleeper returned no projections for week {current}")
    for week, frame in zip(weeks, frames, strict=True):
        if frame.height == 0 and week != current:
            print(f"warning: no projections yet for week {week} (keeping any earlier snapshot)")
    new = pl.concat(frames)
    new = store.with_archive("sleeper_proj_snapshots", new, data_dir)
    scored = [
        scored_latest(new, json.loads(lg["scoring_settings"])).with_columns(
            pl.lit(lg["league_id"]).alias("league_id")
        )
        for lg in leagues.iter_rows(named=True)
    ]
    out = pl.concat(scored).select(*store.SCHEMAS["proj_sleeper"])
    # everything is computed before the first write; the derived table is rebuilt from the archive
    store.write_table("sleeper_proj_snapshots", new, "archive", data_dir)
    store.write_table("proj_sleeper", out, "derived", data_dir)
    return new.height


if __name__ == "__main__":
    print(f"{run()} rows in the archive")
