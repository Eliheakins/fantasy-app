"""Turn the player index into the static `players.json` the browser searches and matches against."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import polars as pl

from pipeline.atomic import atomic_path
from schemas.manifest import JsonFileEntry
from schemas.players import PlayerEntry, PlayersFile

PLAYERS_FILENAME = "players.json"
PLAYER_INDEX_FILENAME = "player_index.parquet"
_OPTIONAL = ("position", "team", "headshot_url", "birth_date", "years_exp")


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def build_players(index: pl.DataFrame) -> tuple[list[PlayerEntry], int]:
    """Players that have an id and a name, plus how many rows were left out for lacking one."""
    missing = [c for c in ("gsis_id", "full_name") if c not in index.columns]
    if missing:
        raise ValueError(f"The player index lacks {', '.join(missing)}; rebuild the data.")

    wanted = ["gsis_id", "full_name", *(c for c in _OPTIONAL if c in index.columns)]
    players: list[PlayerEntry] = []
    skipped = 0
    for row in index.select(wanted).iter_rows(named=True):
        gsis_id, name = _text(row["gsis_id"]), _text(row["full_name"])
        if gsis_id is None or name is None:
            skipped += 1
            continue
        born = row.get("birth_date")
        years = row.get("years_exp")
        players.append(
            PlayerEntry(
                gsis_id=gsis_id,
                full_name=name,
                position=_text(row.get("position")),
                team=_text(row.get("team")),
                headshot_url=_text(row.get("headshot_url")),
                birth_date=born.isoformat() if isinstance(born, date) else _text(born),
                years_exp=int(years) if years is not None else None,
            )
        )
    return players, skipped


def write_players_file(data_dir: Path) -> tuple[JsonFileEntry, int]:
    """Write `players.json` atomically; returns its manifest entry and the skipped-row count."""
    source = data_dir / PLAYER_INDEX_FILENAME
    if not source.is_file():
        raise FileNotFoundError(f"{PLAYER_INDEX_FILENAME} not found in {data_dir}; build it first.")
    players, skipped = build_players(pl.read_parquet(source))
    with atomic_path(data_dir / PLAYERS_FILENAME) as tmp:
        tmp.write_text(PlayersFile(players=players).model_dump_json(), encoding="utf-8")
    return JsonFileEntry(path=PLAYERS_FILENAME, rows=len(players)), skipped
