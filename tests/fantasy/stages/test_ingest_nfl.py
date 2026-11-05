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


def test_a_game_day_that_ended_after_the_file_was_written_makes_it_stale() -> None:
    import datetime as dt

    def ts(day: str) -> float:
        return dt.datetime.fromisoformat(day).replace(tzinfo=dt.UTC).timestamp()

    written, now = ts("2026-10-18T20:00:00"), ts("2026-10-19T12:00:00")
    assert i.game_day_ended_since(["2026-10-18"], written, now)
    assert not i.game_day_ended_since(["2026-10-25"], written, now)
    assert not i.game_day_ended_since(["2026-10-18"], ts("2026-10-19T08:00:00"), now)


def test_replacement_is_refused_when_empty_older_or_newly_null(tmp_path) -> None:
    old = pl.DataFrame({"season": [2026], "week": [6], "x": [1.0]})
    store.table_path("tbl", "raw", tmp_path).parent.mkdir(parents=True)
    old.write_parquet(store.table_path("tbl", "raw", tmp_path))
    good = pl.DataFrame({"season": [2026], "week": [7], "x": [2.0]})
    i.check_replacement("tbl", good, None, tmp_path)
    for bad in (
        good.clear(),
        good.with_columns(week=pl.lit(5)),
        good.with_columns(x=pl.lit(None, dtype=pl.Float64)),
    ):
        with pytest.raises(ValueError):
            i.check_replacement("tbl", bad, None, tmp_path)
