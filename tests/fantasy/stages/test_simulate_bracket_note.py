"""The simulate stage says so when the playoffs have started but no bracket rows were synced."""

from pathlib import Path

import polars as pl
import pytest
from store_fixture import engine_store, write_rows

from fantasy import _runs, store
from fantasy.stages import simulate as sim_stage

SIMS = 50


def _run(tmp_path: Path, start: int, bracket: list[dict]) -> list[str]:
    engine_store(tmp_path)
    leagues = store.read_table("leagues", "raw", tmp_path).with_columns(
        playoff_week_start=pl.lit(start, pl.Int64)
    )
    store.write_table("leagues", leagues, "raw", tmp_path)
    write_rows(tmp_path, "playoff_brackets", bracket, area="raw")
    _runs._soft_failures.clear()
    sim_stage.run(n_sims=SIMS, archive=False, data_dir=tmp_path)
    notes = list(_runs._soft_failures)
    _runs._soft_failures.clear()
    return notes


# week 3 is current; in the first playoff week Sleeper may not have fixed the bracket yet
@pytest.mark.parametrize(("start", "noted"), [(2, True), (3, False), (4, False)])
def test_playoffs_without_bracket_rows_are_a_soft_failure(
    tmp_path: Path, start: int, noted: bool
) -> None:
    notes = _run(tmp_path, start, [])
    assert any("no bracket rows" in n for n in notes) is noted


def test_only_provisional_rows_a_week_into_the_playoffs_are_a_soft_failure(
    tmp_path: Path,
) -> None:
    final = {"league_id": "L1", "bracket": "winners", "r": 1, "m": 1, "t1": 1, "t2": 2, "p": 1}
    notes = _run(tmp_path, 2, [final | {"fetched_week": 1}])
    assert any("no bracket rows" in n for n in notes)


def test_synced_bracket_rows_are_no_soft_failure(tmp_path: Path) -> None:
    final = {"league_id": "L1", "bracket": "winners", "r": 1, "m": 1, "t1": 1, "t2": 2, "p": 1}
    synced = final | {"fetched_week": 2}
    assert not any("no bracket rows" in n for n in _run(tmp_path, 2, [synced]))
