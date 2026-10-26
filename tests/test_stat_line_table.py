import os
from pathlib import Path

import polars as pl
import pytest

from fantasy import stat_line_table as slt
from fantasy import store

Q = pl.DataFrame({"gsis_id": ["A"], "season": [2026], "week": [7], "q": [0.8]})


def write_learned(data_dir: Path) -> None:
    store.write_table(
        "proj_learned", pl.DataFrame(schema=store.SCHEMAS["proj_learned"]), "derived", data_dir
    )


def test_the_table_is_used_only_when_it_is_as_new_as_the_learned_projections(
    tmp_path: Path,
) -> None:
    write_learned(tmp_path)
    assert slt.stored(tmp_path) is None  # no table: the projections carry no q
    slt.sync(Q, tmp_path)
    assert slt.stored(tmp_path)["q"].to_list() == [0.8]  # type: ignore[index]
    learned = store.table_path("proj_learned", "derived", tmp_path)
    later = store.table_path(slt.NAME, "derived", tmp_path).stat().st_mtime_ns + 10**9
    os.utime(learned, ns=(later, later))  # learn ran again without writing it
    with pytest.warns(UserWarning, match="older than proj_learned"):
        assert slt.stored(tmp_path) is None


def test_sync_deletes_the_table_when_the_switch_is_off(tmp_path: Path) -> None:
    slt.sync(Q, tmp_path)
    slt.sync(None, tmp_path)
    assert not store.table_path(slt.NAME, "derived", tmp_path).exists()
    slt.sync(None, tmp_path)  # nothing to delete is fine


def test_scale_and_divide_use_q_and_fail_on_a_missing_chance() -> None:
    frame = pl.DataFrame({"gsis_id": ["A", "B"], "projection": [10.0, 4.0]})
    chance = pl.DataFrame({"gsis_id": ["A", "B"], "q": [0.8, 0.5]})
    assert slt.scale(frame, chance, ["gsis_id"])["projection"].to_list() == [8.0, 2.0]
    assert slt.divide(frame, chance, ["gsis_id"])["projection"].to_list() == [12.5, 8.0]
    with pytest.raises(ValueError, match="no stat-line chance"):
        slt.divide(frame, chance.head(1), ["gsis_id"])


def test_simulate_takes_this_seasons_games_from_the_current_week(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fantasy.stages import simulate

    table = pl.DataFrame(
        {
            "gsis_id": ["A"] * 3,
            "season": [2025, 2026, 2026],
            "week": [8, 6, 8],
            "q": [0.1, 0.2, 0.3],
        }
    )
    monkeypatch.setattr(slt, "stored", lambda data_dir=None: table)
    assert simulate._stat_line(7) == {("A", 8): 0.3}  # config season 2026
    monkeypatch.setattr(slt, "stored", lambda data_dir=None: None)
    assert simulate._stat_line(7) is None
