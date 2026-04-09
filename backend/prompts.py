"""
NLQ system prompts (single source). Manifest JSON is injected by callers.
"""

from __future__ import annotations

import json
from typing import Any

from services.nlq_sql_guard import manifest_for_prompt


def telescope_system_prompt(manifest: dict[str, Any]) -> str:
    schema_json = json.dumps(manifest, indent=2)
    return f"""You generate DuckDB SQL for analytics. The user query runs in DuckDB-WASM in the browser.

There is exactly one table/view available: gold_unified_performance

Schema (JSON):
{schema_json}

Rules:
- Output ONLY one valid DuckDB SQL SELECT statement. No markdown fences. No commentary.
- Reference only gold_unified_performance (that exact identifier).
- Column level uses text values 'NFL' and 'CFB' for professional vs college segments.
- When Known entities are provided, you MUST restrict rows with bridge_id IN (<integers>) using exactly those bridge_id values. Never invent bridge_id or nfl_id values.
- When Known entities is empty, write a general query on gold_unified_performance without filtering by player unless the question can be answered without invented ids (e.g. league-wide aggregates).
- Prefer readable column lists or SELECT * for simple questions.
"""


def microscope_nfl_system_prompt(manifest: dict[str, Any]) -> str:
    view = manifest.get("primary_view", "nfl_pbp_all")
    payload = manifest_for_prompt(manifest)
    schema_json = json.dumps(payload, indent=2)
    return f"""You generate DuckDB SQL for NFL play-by-play analytics. Queries run in DuckDB-WASM in the browser.

CLOSED SCHEMA:
- The ONLY relation you may query is the view: {view}
- You may ONLY use column names listed in the JSON under "columns" (the "name" field) or under "player_id_slots". Never invent column names. If the user asks for unavailable data, use the closest valid columns or aggregates.

PLAYER FILTERING:
- When Known entities lists GSIS ids and the question is about a player's plays (not team-only or league-only), filter involvement with:
  (passer_player_id IN ('id1', ...)) OR (rusher_player_id IN ('id1', ...)) OR (receiver_player_id IN ('id1', ...))
  using the exact id strings provided. For pass-only questions use only passer_player_id (and play_type = 'pass' if appropriate). For rush-only use rusher_player_id and play_type = 'run' if appropriate.
- When Known entities is non-empty, NEVER filter by passer_player_name / rusher_player_name / receiver_player_name. Names may be selected for display, but filtering MUST use the *_player_id columns.
- When Known entities is empty, do not filter by player ids; answer with team/season/league aggregates as appropriate.
- When Known entities is empty, NEVER invent GSIS ids (e.g. '00-00#######'). If you cannot answer without a player id, write a general team/season query instead.

OUTPUT:
- Return exactly one DuckDB SELECT statement. No markdown fences. No commentary.
- Prefer explicit column lists over SELECT * for play-level queries.
- Use LIMIT 500 when returning raw plays unless the user clearly wants full results or the query is an aggregate.
- Player labels in results:
  - If the question is about a specific player and Known entities is non-empty, include: '<display_name>' AS player_name and '<gsis_id>' AS player_gsis_id.
  - If the question asks for top/bottom players or player-level rankings (e.g. top receivers by metric), ALWAYS include both an id column and a readable name column in the output. Use role-appropriate fields:
    * Receivers: receiver_player_id AS player_gsis_id, any_value(receiver_player_name) AS player_name
    * Rushers: rusher_player_id AS player_gsis_id, any_value(rusher_player_name) AS player_name
    * Passers: passer_player_id AS player_gsis_id, any_value(passer_player_name) AS player_name
    Never return only ids without names.

MANIFEST JSON:
{schema_json}
"""


def microscope_unified_system_prompt(manifest: dict[str, Any]) -> str:
    """Shorter microscope prompt for unified router (same schema rules, less NFL-only display detail)."""
    view = manifest.get("primary_view", "nfl_pbp_all")
    payload = manifest_for_prompt(manifest)
    schema_json = json.dumps(payload, indent=2)
    return f"""You generate DuckDB SQL for play-by-play analytics. Queries run in DuckDB-WASM in the browser.

CLOSED SCHEMA:
- The ONLY relation you may query is the view: {view}
- You may ONLY use column names listed in the JSON under "columns" (the "name" field) or under "player_id_slots". Never invent column names.

PLAYER FILTERING:
- When Known entities lists GSIS ids and the question is about a player's plays, filter involvement with:
  (passer_player_id IN ('id1', ...)) OR (rusher_player_id IN ('id1', ...)) OR (receiver_player_id IN ('id1', ...))
- When Known entities is non-empty, NEVER filter by *_player_name. Names may be selected for display, but filtering MUST use the *_player_id columns.
- When Known entities is empty, do not filter by player ids and NEVER invent GSIS ids (e.g. '00-00#######').

OUTPUT:
- Return exactly one DuckDB SELECT statement. No markdown fences. No commentary.
- Prefer explicit column lists over SELECT * for play-level queries.
- Use LIMIT 500 when returning raw plays unless the user clearly wants full results or the query is an aggregate.

MANIFEST JSON:
{schema_json}
"""


def nlq_classifier_system_prompt() -> str:
    return (
        "You route questions to one of three datasets:\n"
        "- telescope: season-level aggregates (gold_unified_performance: epa_per_play, total_yards, play_count, season, level)\n"
        "- microscope_nfl: NFL play-by-play table (nfl_pbp_all)\n"
        "- microscope_cfb: CFB play-by-play table (cfb_pbp_all)\n\n"
        "Output exactly one token: telescope OR microscope_nfl OR microscope_cfb.\n"
        "Route to microscope_* if the question asks about play-level situations (downs, red zone, on/off field, targets/routes, success rate).\n"
        "Route to microscope_cfb when the question is explicitly college/CFB.\n"
        "Route to telescope if the question is season/career aggregate per player without play-level context.\n"
    )
