"""
Each metric's own SQL, run on the built shards, must reproduce the figures recorded in
`metrics/metrics.json` (taken from the tier-1 `player_game` table, nflverse's official totals).

A case is skipped when the shard for its season is not built. Run
`make stat-data` first to exercise them all. The query composition
(role column, play type, play filter) mirrors `runStatQuery` in the frontend engine; the engine's
own tests pin that side.
"""

from __future__ import annotations

import duckdb
import polars as pl
import pytest

from nfl_stat.core.config import DEFAULT_DATA_DIR
from nfl_stat.pipeline.player_game import PLAYER_GAME_COLUMNS, PLAYER_GAME_FILENAME
from nfl_stat.schemas.metrics import MetricDefinition, ReferenceValue, load_metrics

DATA_DIR = DEFAULT_DATA_DIR.resolve()
ROLE_COLUMN = {
    "passer": "passer_player_id",
    "rusher": "rusher_player_id",
    "receiver": "receiver_player_id",
}


def _cases() -> list[tuple[MetricDefinition, ReferenceValue]]:
    # A derived metric has no SQL of its own: referenceValues.test.ts (web) checks it.
    return [
        (m, ref) for m in load_metrics().metrics if m.source == "pbp" for ref in m.reference_values
    ]


def _metric_value(metric: MetricDefinition, ref: ReferenceValue, shard: str) -> float:
    """What the app computes for one player-season, minus the filter chips."""
    assert metric.player_role is not None, f"{metric.id}: a pbp metric needs a player role"
    where = [f"{ROLE_COLUMN[metric.player_role]} = ?", "season = ?", "season_type = ?"]
    params: list[object] = [shard, ref.gsis_id, ref.season, ref.season_type]
    if metric.play_type != "all":
        where.append("play_type = ?")
        params.append(metric.play_type)
    if metric.play_filter:
        where.append(f"({metric.play_filter})")

    con = duckdb.connect()
    try:
        row = con.execute(
            f"SELECT {metric.base_sql} FROM read_parquet(?) WHERE {' AND '.join(where)}",
            params,
        ).fetchone()
    finally:
        con.close()
    assert row is not None and row[0] is not None, "the metric returned no value"
    return float(row[0])


@pytest.mark.parametrize(
    ("metric", "ref"),
    _cases(),
    ids=lambda v: v.id if isinstance(v, MetricDefinition) else f"{v.player}-{v.season}",
)
def test_metric_sql_reproduces_its_reference_value(metric: MetricDefinition, ref: ReferenceValue):
    shard = DATA_DIR / f"nfl_pbp_{ref.season}.parquet"
    if not shard.exists():
        pytest.skip(f"no play-by-play shard built for {ref.season}")

    value = _metric_value(metric, ref, str(shard))

    allowed = abs(ref.value) * ref.tolerance
    assert abs(value - ref.value) <= allowed, (
        f"{metric.id} for {ref.player} {ref.season} {ref.season_type}: got {value:.4f}, "
        f"expected {ref.value} (tolerance {ref.tolerance:.1%}, source: {ref.source})"
    )


def test_there_are_reference_values_to_check():
    assert len(_cases()) >= 15


def _player_game_cases() -> list[tuple[MetricDefinition, ReferenceValue]]:
    return [(m, ref) for m, ref in _cases() if m.player_game_column]


def test_every_player_game_column_exists_and_belongs_to_a_counting_stat():
    for metric in load_metrics().metrics:
        if metric.player_game_column:
            assert metric.player_game_column in PLAYER_GAME_COLUMNS, metric.id
            assert not metric.rate_only, f"{metric.id} is a rate, so it cannot be a table total"


@pytest.mark.parametrize(
    ("metric", "ref"),
    _player_game_cases(),
    ids=lambda v: v.id if isinstance(v, MetricDefinition) else f"{v.player}-{v.season}",
)
def test_player_game_total_matches_the_official_reference_value(
    metric: MetricDefinition, ref: ReferenceValue
):
    table = DATA_DIR / PLAYER_GAME_FILENAME
    if not table.exists():
        pytest.skip("no player-game table built")

    column = metric.player_game_column
    assert column is not None, f"{metric.id}: a player-game case needs a column"
    total = float(
        pl.read_parquet(table)
        .filter(
            (pl.col("gsis_id") == ref.gsis_id)
            & (pl.col("season") == ref.season)
            & (pl.col("season_type") == ref.season_type)
        )[column]
        .sum()
    )

    assert abs(total - ref.value) <= abs(ref.value) * ref.tolerance, (
        f"{metric.id} for {ref.player}: table says {total}, reference says {ref.value}"
    )
