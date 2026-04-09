"""
Heuristic SQL guardrails for Microscope NLQ (NFL/CFB play-by-play).

Public API for routers and unified NLQ — do not import private helpers from nlq_microscope.
"""

from __future__ import annotations

import re
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MicroscopeIdEntity(Protocol):
    """Entity with a string player id (GSIS or ESPN) and display name."""

    gsis_id: str
    display_name: str


def manifest_for_prompt(manifest: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in manifest.items() if not str(k).startswith("_")}


def enforce_entity_id_filter(
    sql: str,
    *,
    entities: list[MicroscopeIdEntity],
    player_id_slots: list[str],
) -> None:
    if not entities:
        return

    ids = [e.gsis_id.strip() for e in entities if e.gsis_id and e.gsis_id.strip()]
    if not ids:
        return

    low = sql.lower()
    if not any(slot.lower() in low for slot in player_id_slots):
        raise ValueError("When Known entities is non-empty, SQL must reference a player_id slot column.")

    name_pred = re.compile(r"\b(?:passer|rusher|receiver)_player_name\b\s*(?:=|in)\s*\(", re.IGNORECASE)
    name_eq = re.compile(r"\b(?:passer|rusher|receiver)_player_name\b\s*=", re.IGNORECASE)
    if name_pred.search(sql) or name_eq.search(sql):
        raise ValueError("When Known entities is non-empty, do not filter by *_player_name; filter by *_player_id.")

    if not any((f"'{pid.lower()}'" in low) or (pid.lower() in low) for pid in ids):
        raise ValueError("When Known entities is non-empty, SQL must include at least one provided gsis_id literal.")


def reject_hallucinated_gsis_ids_when_no_entities(
    sql: str,
    *,
    entities: list[MicroscopeIdEntity],
    player_id_slots: list[str],
) -> None:
    if entities:
        return

    low = sql.lower()
    if not any(slot.lower() in low for slot in player_id_slots):
        return

    gsis_literal = re.compile(r"'00-00\d{7}'", re.IGNORECASE)
    if gsis_literal.search(sql):
        raise ValueError(
            "No player ids were resolved locally, but SQL contains a GSIS-looking id literal. "
            "Do not invent ids; either omit player_id filtering or retry with a clearer player name."
        )


def reject_hallucinated_espn_ids_when_no_entities(
    sql: str,
    *,
    entities: list[MicroscopeIdEntity],
    player_id_slots: list[str],
) -> None:
    if entities:
        return
    low = sql.lower()
    if not any(slot.lower() in low for slot in player_id_slots):
        return
    if re.search(r"'[0-9]{4,10}'", sql):
        raise ValueError(
            "No CFB player ids were resolved locally, but SQL contains an ESPN-looking id literal. "
            "Do not invent ids; omit player_id filtering or retry with a clearer player name."
        )


def enforce_player_labels_in_results(sql: str, *, player_id_slots: list[str]) -> None:
    low = sql.lower()
    role_pairs = [
        ("passer_player_id", "passer_player_name"),
        ("rusher_player_id", "rusher_player_name"),
        ("receiver_player_id", "receiver_player_name"),
    ]
    allowed = {s.lower() for s in player_id_slots or []}
    for pid, pname in role_pairs:
        if pid.lower() not in allowed:
            continue
        grouped = re.search(rf"\bgroup\s+by\b[\s\S]*?\b{re.escape(pid.lower())}\b", low) is not None
        selected = re.search(rf"\b{re.escape(pid.lower())}\b", low) is not None
        if (grouped or selected) and (pname.lower() not in low):
            raise ValueError(
                f"Query references {pid} but does not include {pname}. "
                f"When returning player-level results, include a name column (e.g. any_value({pname}) AS player_name)."
            )
