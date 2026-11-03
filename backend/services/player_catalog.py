from __future__ import annotations

from pathlib import Path

import polars as pl

from schemas.api import PlayerDictionaryRow, PlayerRecord


def normalize_gsis_id_expr(col: pl.Expr) -> pl.Expr:
    """Compare GSIS ids as strings (parquet may store Utf8 or other types)."""
    return col.cast(pl.Utf8).str.strip_chars()


def load_player_index_from_path(path: Path) -> pl.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Player index not found: {path}")
    return pl.read_parquet(path)


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


def player_dictionary(df: pl.DataFrame) -> list[PlayerDictionaryRow]:
    """Players with an id and a name; position/team let the UI tell namesakes apart."""
    wanted = [c for c in ("gsis_id", "full_name", "position", "team") if c in df.columns]
    rows: list[PlayerDictionaryRow] = []
    for r in df.select(wanted).iter_rows(named=True):
        gsis_id = str(r.get("gsis_id") or "").strip()
        name = str(r.get("full_name") or "").strip()
        if not gsis_id or not name:
            continue
        rows.append(
            PlayerDictionaryRow(
                gsis_id=gsis_id,
                display_name=name,
                search_key=name.lower(),
                position=r.get("position"),
                team=r.get("team"),
            )
        )
    return rows
