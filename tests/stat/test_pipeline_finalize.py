from __future__ import annotations

import polars as pl
import pytest

from nfl_stat.pipeline import nfl_pipeline
from nfl_stat.pipeline.nfl_pipeline import (
    PART_COLS,
    finalize_columns,
    format_null_report,
    null_report,
)


def _frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [2023, 2023, 2023],
            "week": [1, 1, 1],
            "passer_player_id": ["a", "b", None],
            "offense_personnel": ["11", None, "12"],
            "defenders_in_box": [6, None, 7],
            "number_of_pass_rushers": [0, None, 4],
            "avg_separation": [3.2, None, 0.0],
            "avg_time_to_throw": [2.6, None, None],
        }
    )


def test_missing_participation_and_ngs_values_stay_null():
    out = finalize_columns(_frame())

    assert out["offense_personnel"].to_list() == ["11", None, "12"]
    assert out["defenders_in_box"].to_list() == [6, None, 7]
    assert out["avg_separation"].to_list() == [3.2, None, 0.0]
    assert out["avg_time_to_throw"].null_count() == 2


def test_a_real_zero_is_kept_and_distinct_from_missing():
    out = finalize_columns(_frame())

    assert out["number_of_pass_rushers"].to_list() == [0, None, 4]


def test_columns_are_cast_to_their_storage_types():
    out = finalize_columns(_frame())

    assert out.schema["defenders_in_box"] == pl.Int32
    assert out.schema["number_of_pass_rushers"] == pl.Int32
    assert out.schema["offense_personnel"] == pl.String
    assert out.schema["avg_separation"] == pl.Float64
    assert out.schema["season"] == pl.Int32
    assert out.schema["passer_player_id"] == pl.String


def test_finalize_ignores_columns_that_are_not_present():
    out = finalize_columns(pl.DataFrame({"season": [2023], "week": [1]}))

    assert out.columns == ["season", "week"]


def test_season_without_participation_gets_typed_null_columns(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(nfl_pipeline, "get_current_season", lambda roster=False: 2026)
    pbp = pl.DataFrame({"play_id": [1, 2], "old_game_id": ["g", "g"]})

    out = nfl_pipeline._join_participation_for_year(pbp, 2026)

    assert set(PART_COLS) <= set(out.columns)
    assert all(out[c].null_count() == 2 for c in PART_COLS)
    final = finalize_columns(
        out.with_columns(pl.lit(2026).alias("season"), pl.lit(1).alias("week"))
    )
    assert final.schema["defenders_in_box"] == pl.Int32
    assert final.schema["offense_personnel"] == pl.String


def test_null_report_gives_the_share_of_missing_values_per_column():
    report = null_report(_frame())

    assert report["avg_separation"] == pytest.approx(1 / 3)
    assert report["avg_time_to_throw"] == pytest.approx(2 / 3)
    assert report["number_of_pass_rushers"] == pytest.approx(1 / 3)
    assert "season" not in report


def test_null_report_is_empty_for_an_empty_frame():
    assert null_report(_frame().clear()) == {}


def test_format_null_report_lists_columns_with_percentages():
    text = format_null_report({"avg_separation": 0.5, "defenders_in_box": 0.0})

    assert "avg_separation" in text
    assert "50%" in text
    assert "defenders_in_box" in text
