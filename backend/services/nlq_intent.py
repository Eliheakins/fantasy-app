"""
Question -> structured query intent (stat ids, filter ids, granularity) via the local model.

The model never writes queries. The frontend's engine runs the intent, and player ids are
resolved in the browser, so the model cannot invent either.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from openai import AsyncOpenAI
from pydantic import ValidationError

from schemas.nlq import (
    MAX_INTENT_STATS,
    CatalogFilter,
    CatalogStat,
    IntentOutcome,
    IntentRequest,
    QueryIntent,
    QueryOutcome,
    UnsupportedOutcome,
)
from services.llm_client import ChatMessage, chat_text

MAX_ATTEMPTS = 2

_FENCE_START = re.compile(r"^```(?:json)?\s*", re.IGNORECASE)
_FENCE_END = re.compile(r"\s*```$")

# (question, intent) pairs shown to the model; only used when every id exists in the catalog.
_EXAMPLES: list[tuple[str, dict[str, Any]]] = [
    (
        "Mahomes passing yards and touchdowns in 2023",
        {
            "stat_ids": ["pass_yards", "pass_tds"],
            "filter_ids": ["season-2023"],
            "granularity": "total",
        },
    ),
    (
        "Kelce receptions per game in the 2022 playoffs",
        {
            "stat_ids": ["rec_receptions"],
            "filter_ids": ["season-2022", "stype-post"],
            "granularity": "per_game",
        },
    ),
    (
        "Compare Lamar Jackson and Josh Allen EPA per play on 3rd down",
        {"stat_ids": ["eff_epa"], "filter_ids": ["down-3"], "granularity": "per_play"},
    ),
    (
        "Derrick Henry rushing yards per game in the second half",
        {
            "stat_ids": ["rush_yards"],
            "filter_ids": ["gclk-second-half"],
            "granularity": "per_game",
        },
    ),
]


class IntentError(ValueError):
    """The model reply could not be turned into a valid intent; the message is fed back to it."""


def _example_block(stat_ids: set[str], filter_ids: set[str]) -> str:
    lines: list[str] = []
    for question, intent in _EXAMPLES:
        if set(intent["stat_ids"]) <= stat_ids and set(intent["filter_ids"]) <= filter_ids:
            lines.append(f"Question: {question}\n{json.dumps(intent)}")
    return "\n\n".join(lines)


def _stat_line(stat: CatalogStat) -> str:
    line = f"{stat.id} | {stat.label} | {stat.category}"
    if stat.aliases:
        aliases = (" ".join(a.split()) for a in stat.aliases)  # no newline can fake a catalog line
        line += f" | also called: {', '.join(aliases)}"
    return line


def build_system_prompt(stats: Sequence[CatalogStat], filters: Sequence[CatalogFilter]) -> str:
    stat_lines = "\n".join(_stat_line(s) for s in stats)
    filter_lines = "\n".join(f"{f.id} | {f.group}: {f.label}" for f in filters)
    examples = _example_block({s.id for s in stats}, {f.id for f in filters})
    examples_section = f"\nEXAMPLES:\n{examples}\n" if examples else ""
    return f"""You turn NFL stat questions into a JSON query for a stats tool.

Reply with ONLY one JSON object, no prose and no code fences:
{{"stat_ids": [...], "filter_ids": [...], "granularity": "total" | "per_game" | "per_play"}}

Rules:
- stat_ids: 1 to {MAX_INTENT_STATS} ids from STATS that answer the question. Never invent ids.
- filter_ids: ids from FILTERS for situations in the question (years, downs, quarters, playoffs, \
home/away, red zone, weather). Empty list if none apply.
- granularity: "per_game" when the question says per game, "per_play" for per play, per attempt or \
efficiency wording, otherwise "total".
- Player names are handled elsewhere. Ignore them.
- If no STATS entry can answer the question (salary, fantasy points, awards, opinions such as \
who is better, team records), reply instead with \
{{"unsupported": "<one short sentence saying why>"}}. \
Never pick a loosely related stat to fill the gap.
{examples_section}
STATS (id | label | category | also called):
{stat_lines}

FILTERS (id | group: label):
{filter_lines}
"""


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = _FENCE_END.sub("", _FENCE_START.sub("", text.strip())).strip()
    start = cleaned.find("{")
    if start == -1:
        raise IntentError("No JSON object found in the reply.")
    try:
        obj, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    except json.JSONDecodeError as e:
        raise IntentError(f"Invalid JSON ({e.msg}).") from e
    if not isinstance(obj, dict):
        raise IntentError("The top-level JSON value must be an object.")
    return obj


def parse_intent(text: str, *, stat_ids: set[str], filter_ids: set[str]) -> QueryIntent:
    obj = extract_json_object(text)
    try:
        intent = QueryIntent.model_validate(obj)
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()
        )
        raise IntentError(f"Wrong shape ({problems}).") from e

    unknown_stats = [i for i in intent.stat_ids if i not in stat_ids]
    if unknown_stats:
        raise IntentError(f"Unknown stat_ids {unknown_stats}. Use only ids from STATS.")
    unknown_filters = [i for i in intent.filter_ids if i not in filter_ids]
    if unknown_filters:
        raise IntentError(f"Unknown filter_ids {unknown_filters}. Use only ids from FILTERS.")

    # Dedupe in order; the builder only takes MAX_INTENT_STATS stats.
    return intent.model_copy(
        update={
            "stat_ids": list(dict.fromkeys(intent.stat_ids))[:MAX_INTENT_STATS],
            "filter_ids": list(dict.fromkeys(intent.filter_ids)),
        }
    )


def parse_reply(text: str, *, stat_ids: set[str], filter_ids: set[str]) -> IntentOutcome:
    obj = extract_json_object(text)
    reason = obj.get("unsupported")
    if (
        reason is None or reason is False
    ):  # the model sometimes writes null/false beside a real query
        return QueryOutcome(intent=parse_intent(text, stat_ids=stat_ids, filter_ids=filter_ids))
    if not isinstance(reason, str) or not reason.strip():
        raise IntentError('"unsupported" needs a short reason sentence.')
    return UnsupportedOutcome(reason=reason.strip()[:300])


async def translate_question(
    *, client: AsyncOpenAI, model: str, req: IntentRequest
) -> IntentOutcome:
    """Ask the model; on an invalid reply, show it the error and ask once more."""
    messages: list[ChatMessage] = [
        {"role": "system", "content": build_system_prompt(req.stats, req.filters)},
        {"role": "user", "content": f"Question: {req.question}"},
    ]
    stat_ids = {s.id for s in req.stats}
    filter_ids = {f.id for f in req.filters}

    last_error = IntentError("No attempt was made.")
    for _ in range(MAX_ATTEMPTS):
        raw = await chat_text(client=client, model=model, messages=messages)
        try:
            return parse_reply(raw, stat_ids=stat_ids, filter_ids=filter_ids)
        except IntentError as e:
            last_error = e
            messages = [
                *messages,
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        f"That reply was invalid: {e} Reply with only the corrected JSON object."
                    ),
                },
            ]
    raise last_error
