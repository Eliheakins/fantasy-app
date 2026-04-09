"""
DynastyProcess `db_playerids.csv` → deduplicated player hub rows (Polars).

Used by `rosetta_layer.build_rosetta_layer` for `player_hub.parquet` and DuckDB.
"""

from __future__ import annotations

import polars as pl

DYNASTY_PLAYERIDS_URL = (
    "https://raw.githubusercontent.com/dynastyprocess/data/master/files/db_playerids.csv"
)


def load_deduped_player_hub() -> pl.DataFrame:
    """
    Load ID map, normalize nulls, filter to NFL and/or ESPN IDs, dedupe, assign integer bridge_id.

    Dedupe key: `gsis_id` when present, else `espn_id` (college-only rows).
    Primary row: non-null `gsis_id` first, then `db_season` DESC, then non-null `espn_id`, then `name`.
    """
    df = pl.read_csv(
        DYNASTY_PLAYERIDS_URL,
        null_values=["NA", "N/A", ""],
        infer_schema_length=10_000,
    )

    if "gsis_id" in df.columns:
        df = df.with_columns(pl.col("gsis_id").cast(pl.Utf8).str.strip_chars().alias("gsis_id"))
        df = df.with_columns(
            pl.when(pl.col("gsis_id") == "").then(None).otherwise(pl.col("gsis_id")).alias("gsis_id")
        )

    if "espn_id" not in df.columns:
        raise ValueError("db_playerids.csv missing espn_id column")

    df = df.with_columns(pl.col("espn_id").cast(pl.Int64, strict=False).alias("espn_id"))

    df = df.filter(pl.col("gsis_id").is_not_null() | pl.col("espn_id").is_not_null())

    if "db_season" in df.columns:
        df = df.with_columns(pl.col("db_season").cast(pl.Int64, strict=False).alias("db_season"))
    else:
        df = df.with_columns(pl.lit(None).cast(pl.Int64).alias("db_season"))

    df = df.with_columns(
        [
            pl.col("gsis_id").is_not_null().alias("_gsis_present"),
            pl.col("espn_id").is_not_null().alias("_espn_present"),
        ]
    )

    df = df.with_columns(
        pl.when(pl.col("gsis_id").is_not_null())
        .then(pl.col("gsis_id"))
        .otherwise(pl.col("espn_id").cast(pl.Utf8))
        .alias("_dedupe_key")
    )

    df = df.sort(
        by=["_gsis_present", "db_season", "_espn_present", "name"],
        descending=[True, True, True, False],
        nulls_last=True,
    )
    df = df.unique(subset=["_dedupe_key"], keep="first")

    cfb_id = (
        pl.when(pl.col("espn_id").is_not_null())
        .then(pl.col("espn_id").cast(pl.Utf8))
        .otherwise(None)
        .alias("cfb_id")
    )

    nfl_id = (
        pl.when(pl.col("gsis_id").is_not_null())
        .then(pl.col("gsis_id"))
        .otherwise(None)
        .alias("nfl_id")
    )

    out = df.select(
        [
            pl.col("name").cast(pl.Utf8).str.strip_chars().alias("display_name"),
            nfl_id,
            cfb_id,
            pl.col("position").cast(pl.Utf8),
            pl.col("college").cast(pl.Utf8),
        ]
    )

    out = out.sort(["nfl_id", "cfb_id", "display_name"], nulls_last=True)
    out = out.with_row_index("bridge_id", offset=1)
    out = out.with_columns(pl.col("bridge_id").cast(pl.Int64))

    return out
