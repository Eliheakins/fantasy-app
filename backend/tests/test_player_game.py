from __future__ import annotations

from pathlib import Path

import polars as pl
import pyarrow.parquet as pq
import pytest

from nfl_stat.pipeline.player_game import (
    PLAYER_GAME_COLUMNS,
    merge_player_game,
    normalize_player_game,
    write_player_game,
)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
BUILT = DATA_DIR / "player_game.parquet"

SOURCE_ONLY = {"player_name": "x", "headshot_url": "u", "fantasy_points": 1.5}


def _source(**overrides: list) -> pl.DataFrame:
    """A frame shaped like nflverse's weekly player stats, with extra columns the app ignores."""
    base: dict[str, list] = {
        "player_id": ["00-0033873", "00-0030506", "00-0033873"],
        "player_display_name": ["Patrick Mahomes", "Travis Kelce", "Patrick Mahomes"],
        "position": ["QB", "TE", "QB"],
        "team": ["KC", "KC", "KC"],
        "opponent_team": ["DET", "DET", "JAX"],
        "season": [2023, 2023, 2023],
        "week": [2, 1, 1],
        "season_type": ["REG", "REG", "REG"],
        "completions": [20.0, 0.0, 21.0],
        "attempts": [30.0, 0.0, 39.0],
        "passing_yards": [272.0, 0.0, 226.0],
        "passing_tds": [2.0, 0.0, 2.0],
        "passing_interceptions": [0.0, 0.0, 1.0],
        "sacks_suffered": [1.0, 0.0, 0.0],
        "sack_yards_lost": [5.0, 0.0, 0.0],
        "carries": [3.0, 0.0, 2.0],
        "rushing_yards": [10.0, 0.0, 8.0],
        "rushing_tds": [0.0, 0.0, 0.0],
        "receptions": [0.0, 4.0, 0.0],
        "targets": [0.0, 6.0, 0.0],
        "receiving_yards": [0.0, 43.0, 0.0],
        "receiving_tds": [0.0, 1.0, 0.0],
        "receiving_yards_after_catch": [0.0, 12.0, 0.0],
        "passing_epa": [4.2, None, -1.1],
        "rushing_epa": [0.3, None, 0.1],
        "receiving_epa": [None, 2.5, None],
    }
    base.update(overrides)
    return pl.DataFrame(
        {k: v for k, v in {**base, **{k: [v] * 3 for k, v in SOURCE_ONLY.items()}}.items()}
    )


def test_normalize_renames_ids_and_keeps_only_the_tier_one_columns():
    out = normalize_player_game(_source())

    assert out.columns == PLAYER_GAME_COLUMNS
    assert "headshot_url" not in out.columns
    mahomes = out.filter(pl.col("gsis_id") == "00-0033873")
    assert mahomes["full_name"][0] == "Patrick Mahomes"


def test_counting_stats_are_integers_and_epa_stays_a_float():
    out = normalize_player_game(_source())

    assert out.schema["passing_yards"] == pl.Int32
    assert out.schema["season"] == pl.Int32
    assert out.schema["passing_epa"] == pl.Float64


def test_rows_are_sorted_by_season_player_and_week():
    out = normalize_player_game(_source())

    assert out.select("gsis_id", "week").rows() == [
        ("00-0030506", 1),
        ("00-0033873", 1),
        ("00-0033873", 2),
    ]


def test_missing_epa_is_kept_null_rather_than_zero():
    out = normalize_player_game(_source())

    assert out.filter(pl.col("gsis_id") == "00-0030506")["passing_epa"].to_list() == [None]


def test_rows_without_a_player_id_are_dropped():
    out = normalize_player_game(_source(player_id=["00-0033873", None, "00-0033873"]))

    assert out.height == 2


def test_only_regular_season_and_playoff_rows_are_kept():
    out = normalize_player_game(_source(season_type=["REG", "PRE", "POST"]))

    assert sorted(out["season_type"].to_list()) == ["POST", "REG"]


def test_missing_source_columns_are_named_in_the_error():
    with pytest.raises(ValueError, match="targets"):
        normalize_player_game(_source().drop("targets"))


def test_a_fractional_count_is_rejected_instead_of_truncated():
    with pytest.raises(ValueError, match="passing_yards"):
        normalize_player_game(_source(passing_yards=[272.5, 0.0, 226.0]))


def test_a_nan_count_is_rejected_with_a_readable_message():
    with pytest.raises(ValueError, match="passing_yards"):
        normalize_player_game(_source(passing_yards=[float("nan"), 0.0, 226.0]))


def _tier_one(season: int, player: str = "g1") -> pl.DataFrame:
    return normalize_player_game(
        _source(
            player_id=[player, player, player],
            season=[season, season, season],
            week=[1, 2, 3],
        )
    )


def test_merging_keeps_seasons_that_were_not_rebuilt_and_replaces_ones_that_were():
    existing = pl.concat([_tier_one(2024, "old"), _tier_one(2025, "old")])
    new = _tier_one(2025, "new")

    merged = merge_player_game(existing, new)

    assert merged.select("season", "gsis_id").unique().sort("season").rows() == [
        (2024, "old"),
        (2025, "new"),
    ]
    assert merged.height == 6


def test_merging_with_no_existing_table_returns_the_new_one():
    new = _tier_one(2026)

    assert merge_player_game(None, new).equals(new)


def test_merging_refuses_a_table_with_a_different_shape():
    old = _tier_one(2024).drop("targets")

    with pytest.raises(ValueError, match="different columns"):
        merge_player_game(old, _tier_one(2025))


def test_write_creates_a_compressed_file_with_small_row_groups(tmp_path: Path):
    path = write_player_game(normalize_player_game(_source()), tmp_path, row_group_size=2)

    meta = pq.read_metadata(path)
    assert path.name == "player_game.parquet"
    assert meta.num_rows == 3
    assert meta.num_row_groups == 2
    assert meta.row_group(0).column(0).compression == "ZSTD"


# Known values against the built file. Official figures: a mismatch means the table is wrong.
needs_build = pytest.mark.skipif(
    not BUILT.exists(), reason="needs a local data build (build_data.py)"
)


@pytest.fixture(scope="module")
def reg() -> pl.DataFrame:
    return pl.read_parquet(BUILT).filter(pl.col("season_type") == "REG")


@needs_build
def test_mahomes_2023_matches_the_official_passing_line(reg: pl.DataFrame):
    mahomes = reg.filter((pl.col("full_name") == "Patrick Mahomes") & (pl.col("season") == 2023))

    assert mahomes["passing_yards"].sum() == 4183
    assert mahomes["passing_tds"].sum() == 27


@needs_build
def test_2023_passing_leaders_match_the_official_ranking(reg: pl.DataFrame):
    leaders = (
        reg.filter(pl.col("season") == 2023)
        .group_by("full_name")
        .agg(pl.col("passing_yards").sum())
        .sort("passing_yards", descending=True)
        .head(3)
        .rows()
    )

    assert leaders == [("Tua Tagovailoa", 4624), ("Jared Goff", 4575), ("Dak Prescott", 4516)]
