"""
Each metric's own SQL, run on the built shards, must reproduce the figures recorded in
`metrics/metrics.json` (taken from the tier-1 `player_game` table, nflverse's official totals).

Skipped when no data is built. Run `uv run python -m pipeline.cli` first to exercise it.
"""

from __future__ import annotations

import duckdb
import pytest

from pipeline.cli import data_output_dir
from schemas.metrics import MetricDefinition, ReferenceValue, load_metrics

DATA_DIR = data_output_dir()
SHARDS = sorted(DATA_DIR.glob("nfl_pbp_*.parquet"))
ROLE_COLUMN = {
    "passer": "passer_player_id",
    "rusher": "rusher_player_id",
    "receiver": "receiver_player_id",
}

pytestmark = pytest.mark.skipif(not SHARDS, reason="no play-by-play shards built")


def _cases() -> list[tuple[MetricDefinition, ReferenceValue]]:
    return [(m, ref) for m in load_metrics().metrics for ref in m.reference_values]


def _metric_value(metric: MetricDefinition, ref: ReferenceValue) -> float:
    """What the app computes for one player-season, minus the filter chips."""
    where = [
        f"{ROLE_COLUMN[metric.player_role]} = ?",
        "season = ?",
        "season_type = ?",
    ]
    if metric.play_type != "all":
        where.append(f"play_type = '{metric.play_type}'")
    if metric.play_filter:
        where.append(f"({metric.play_filter})")

    con = duckdb.connect()
    shard_list = ", ".join(f"'{p}'" for p in SHARDS)
    row = con.execute(
        f"SELECT {metric.base_sql} FROM read_parquet([{shard_list}], union_by_name=true)"
        f" WHERE {' AND '.join(where)}",
        [ref.gsis_id, ref.season, ref.season_type],
    ).fetchone()
    assert row is not None and row[0] is not None, "the metric returned no value"
    return float(row[0])


@pytest.mark.parametrize(
    ("metric", "ref"),
    _cases(),
    ids=lambda v: v.id if isinstance(v, MetricDefinition) else f"{v.player}-{v.season}",
)
def test_metric_sql_reproduces_its_reference_value(metric: MetricDefinition, ref: ReferenceValue):
    value = _metric_value(metric, ref)

    allowed = abs(ref.value) * ref.tolerance
    assert abs(value - ref.value) <= allowed, (
        f"{metric.id} for {ref.player} {ref.season} {ref.season_type}: got {value:.4f}, "
        f"expected {ref.value} (tolerance {ref.tolerance:.1%}, source: {ref.source})"
    )


def test_there_are_reference_values_to_check():
    assert len(_cases()) >= 15
