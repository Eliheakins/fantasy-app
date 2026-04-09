from __future__ import annotations

from pathlib import Path

import polars as pl

from schemas.api import PlayerRecord


def normalize_gsis_id_expr(col: pl.Expr) -> pl.Expr:
    """Compare GSIS ids as strings (parquet may store Utf8 or other types)."""
    return col.cast(pl.Utf8).str.strip_chars()


def load_player_index_from_path(path: Path) -> pl.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Player index not found: {path}")
    return pl.read_parquet(path)


def load_player_index_from_url(url: str) -> pl.DataFrame:
    return pl.read_parquet(url)


def search_players_by_name(df: pl.DataFrame, q: str, *, limit: int = 10) -> list[PlayerRecord]:
    needle = q.strip()
    if not needle:
        return []

    filtered = df.filter(
        pl.col("full_name").str.to_lowercase().str.contains(needle.lower(), literal=True)
    ).head(limit)

    return [PlayerRecord.model_validate(r) for r in filtered.to_dicts()]


def get_player_row(df: pl.DataFrame, gsis_id: str) -> PlayerRecord | None:
    target = gsis_id.strip()
    if not target:
        return None

    match = df.filter(normalize_gsis_id_expr(pl.col("gsis_id")) == target)
    if match.height == 0:
        return None
    return PlayerRecord.model_validate(match.to_dicts()[0])
