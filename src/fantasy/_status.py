"""Data freshness: when each source was written, and which optional layers are missing."""

from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from fantasy import store
from fantasy._runs import latest_runs
from fantasy.config import load_config

_FRESHNESS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    "source": pl.String,
    "updated_at": pl.Datetime("us", "UTC"),
    "age_hours": pl.Float64,
}


FRESHNESS_SOURCES = (
    ("Sleeper", "leagues", "raw"),
    ("NFL stats", "nfl_player_stats", "raw"),
    ("Simulation", "sim_season", "derived"),
)


def freshness(now: datetime | None = None, data_dir: Path | None = None) -> pl.DataFrame:
    """When each data source was last written: source, updated_at (UTC), age_hours."""
    now = now or datetime.now(UTC)
    rows = []
    for label, table, area in FRESHNESS_SOURCES:
        path = store.table_path(table, area, data_dir)
        if path.exists():
            updated = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            rows.append((label, updated, (now - updated).total_seconds() / 3600))
    return pl.DataFrame(rows, schema=_FRESHNESS_SCHEMA, orient="row")


def simulation_behind_inputs(data_dir: Path | None = None) -> str | None:
    """A note when the simulation table is older than the Sleeper or NFL inputs (a refresh that
    failed part way leaves mixed vintages), else None."""
    sim = store.table_path("sim_season", "derived", data_dir)
    if not sim.exists():
        return None
    inputs = [store.table_path(t, a, data_dir) for _, t, a in FRESHNESS_SOURCES[:2]]
    behind = [p.stem for p in inputs if p.exists() and p.stat().st_mtime > sim.stat().st_mtime]
    if not behind:
        return None
    return f"Season odds are older than {', '.join(behind)}: the last refresh may have failed"


def refresh_runs(data_dir: Path | None = None) -> pl.DataFrame:
    """The latest recorded outcome of each refresh stage: stage, finished_at, status, error."""
    return latest_runs(data_dir).select("stage", "finished_at", "status", "error")


# projection layers that the simulation skips, without error, when their table is missing
OPTIONAL_LAYERS = (
    ("injury model", "injury_effects", "derived"),
    ("outlook", "outlook_effects", "derived"),
    ("matchup and offense effects", "environment_effects", "derived"),
    ("size calibration", "projection_calibration", "derived"),
    ("Sleeper projections", "proj_sleeper", "derived"),
)


def missing_layers(data_dir: Path | None = None) -> list[str]:
    """Names of projection layers the simulation is running without because a stage did not run."""
    config = load_config()
    layers = [
        layer
        for layer in OPTIONAL_LAYERS
        if config.environment_layer or layer[1] != "environment_effects"
    ]
    if config.projection_model == "learned":
        layers.append(("learned projections", "proj_learned", "derived"))
    missing = [
        label
        for label, table, area in layers
        if not store.table_path(table, area, data_dir).exists()
    ]
    # prop_points writes these for the current week only, so an empty table is a missing source
    labels = {"fftoday": "FFToday projections", "props": "prop lines"}
    for source in [s for s in config.blend_sources if s in labels]:
        table = "proj_props" if source == "props" else "proj_outside"
        path = store.table_path(table, "derived", data_dir)
        rows = pl.scan_parquet(path) if path.exists() else None
        if rows is not None and source != "props":
            rows = rows.filter(pl.col("source") == source)
        if rows is None or rows.select(pl.len()).collect().item() == 0:
            missing.append(labels[source])
    return missing
