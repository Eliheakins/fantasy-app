"""Turn the player index into the static `players.json` the browser searches and matches against."""

from __future__ import annotations

import math
from datetime import date, datetime
from pathlib import Path

import polars as pl
from pydantic import ValidationError

from pipeline.atomic import atomic_path
from schemas.manifest import JsonFileEntry
from schemas.players import PlayerEntry, PlayersFile

PLAYERS_FILENAME = "players.json"
PLAYER_INDEX_FILENAME = "player_index.parquet"
_OPTIONAL = ("position", "team", "headshot_url", "birth_date", "years_exp")


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _https_url(value: object) -> str | None:
    """Image addresses come from third-party data; only https ones are kept."""
    text = _text(value)
    return text if text is not None and text.lower().startswith("https://") else None


def _whole_number(value: object) -> int | None:
    """A whole number, or None for a missing, NaN or fractional value (it must not abort a build)."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return int(number) if math.isfinite(number) and number.is_integer() else None


def _iso_date(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _text(value)


def build_players(index: pl.DataFrame) -> tuple[list[PlayerEntry], int]:
    """Players that have an id and a name, plus how many rows were left out for lacking one.

    An id that repeats keeps its last row.
    """
    missing = [c for c in ("gsis_id", "full_name") if c not in index.columns]
    if missing:
        raise ValueError(f"The player index lacks {', '.join(missing)}; rebuild the data.")

    wanted = ["gsis_id", "full_name", *(c for c in _OPTIONAL if c in index.columns)]
    players: dict[str, PlayerEntry] = {}
    skipped = 0
    for row in index.select(wanted).iter_rows(named=True):
        gsis_id, name = _text(row["gsis_id"]), _text(row["full_name"])
        if gsis_id is None or name is None:
            skipped += 1
            continue
        players[gsis_id] = PlayerEntry(
            gsis_id=gsis_id,
            full_name=name,
            position=_text(row.get("position")),
            team=_text(row.get("team")),
            headshot_url=_https_url(row.get("headshot_url")),
            birth_date=_iso_date(row.get("birth_date")),
            years_exp=_whole_number(row.get("years_exp")),
        )
    return list(players.values()), skipped


def _earlier_players(path: Path) -> list[PlayerEntry]:
    """Players from the previous build, or none if there is no readable file to carry over."""
    try:
        return PlayersFile.model_validate_json(path.read_text(encoding="utf-8")).players
    except (OSError, ValueError, ValidationError):
        return []


def write_players_file(data_dir: Path) -> tuple[JsonFileEntry, int]:
    """Write `players.json` atomically; returns its manifest entry and the skipped-row count.

    A build over a few seasons only knows those seasons' rosters, so players from earlier builds
    who are not in this one stay in the file (retired players still have plays in older shards).
    """
    source = data_dir / PLAYER_INDEX_FILENAME
    if not source.is_file():
        raise FileNotFoundError(f"{PLAYER_INDEX_FILENAME} not found in {data_dir}; build it first.")
    players, skipped = build_players(pl.read_parquet(source))

    target = data_dir / PLAYERS_FILENAME
    current = {p.gsis_id for p in players}
    merged = [*players, *(p for p in _earlier_players(target) if p.gsis_id not in current)]

    with atomic_path(target) as tmp:
        tmp.write_text(PlayersFile(players=merged).model_dump_json(), encoding="utf-8")
    return JsonFileEntry(path=PLAYERS_FILENAME, rows=len(merged)), skipped
