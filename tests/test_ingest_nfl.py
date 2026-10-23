import polars as pl
import pytest

from fantasy import store
from fantasy.stages import ingest_nfl as i


def test_conform_selects_orders_and_casts_registered_columns() -> None:
    raw = pl.DataFrame(
        {
            "season": ["2026"],  # nflverse ff_opportunity sends season as a string
            "week": [6.0],  # and week as a float
            "player_id": ["00-1"],
            "extra": [1],
        }
    )
    schema = {"season": pl.Int64, "week": pl.Int64, "player_id": pl.String}
    store.SCHEMAS["_tmp"] = schema
    try:
        out = i.conform("_tmp", raw)
    finally:
        del store.SCHEMAS["_tmp"]
    assert out.columns == ["season", "week", "player_id"]
    assert out.schema["season"] == pl.Int64 and out["week"].to_list() == [6]


def test_conform_fails_loudly_on_a_missing_column() -> None:
    store.SCHEMAS["_tmp"] = {"season": pl.Int64, "gone": pl.Float64}
    try:
        with pytest.raises(pl.exceptions.ColumnNotFoundError):
            i.conform("_tmp", pl.DataFrame({"season": [2026]}))
    finally:
        del store.SCHEMAS["_tmp"]


def test_snaps_get_gsis_ids_through_the_pfr_id() -> None:
    snaps = pl.DataFrame({"pfr_player_id": ["A", "B"], "offense_snaps": [50.0, 10.0]})
    ffids = pl.DataFrame(
        {"pfr_id": ["A", None, "A"], "gsis_id": ["G1", "G2", "G1"]},
        schema={"pfr_id": pl.String, "gsis_id": pl.String},
    )
    out = i.with_gsis(snaps, ffids)
    assert out.height == 2
    assert out.sort("pfr_player_id")["gsis_id"].to_list() == ["G1", None]


def test_null_ids_are_dropped() -> None:
    df = pl.DataFrame({"player_id": ["a", None, "c"], "x": [1, 2, 3]})
    assert i.drop_null_ids(df, "player_id")["x"].to_list() == [1, 3]
