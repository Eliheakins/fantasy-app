"""
Question -> structured query intent via Jev, TypeSafe's hosted System One model (issue #71).

Jev answers typed questions instead of writing JSON, so one request carries a Noul per stat, a
Noul per non-season filter, a Choice for granularity, a Choice for relative seasons and three
companion Nouls; code turns the probabilities into the same validated outcome as the local
model. Seasons are read in code (Jev is weak at numbers and dates). This is design 2 of
`research/jev_intent_check.py`. Only the question text and the generic catalog are sent.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

import httpx2

from nfl_stat.core.seasons import current_season as _season_now
from nfl_stat.schemas.nlq import (
    MAX_INTENT_STATS,
    IntentOutcome,
    IntentRequest,
    QueryOutcome,
    UnsupportedOutcome,
)
from nfl_stat.services.nlq_intent import IntentError, validate_intent
from nfl_stat.services.undefined_terms import undefined_term

JEV_URL = "https://api.typesafe.ai/v1/systemone"
THRESHOLD = 0.5  # fixed before the #71 runs
MAX_ATTEMPTS = 2
MAX_RETRY_AFTER_S = 2.0  # a 429 asking for a longer wait falls back instead of stalling Ask
DEFAULT_RETRY_S = 0.5
SEASON_GROUP = "Season"
_YEAR = re.compile(r"\b(19\d\d|20\d\d)\b")

GROUP_PHRASE = {
    "Down": "plays on {label} down",
    "Distance to go": "plays with {label} yards to go",
    "Week": "{label} weeks of the season",
    "Location": "{label} games",
    "Field position": "plays in the {label}",
    "Red zone (flag)": "red zone plays",
    "Goal to go": "goal-to-go plays",
    "Season type": "the {label}",
    "Quarter": "the {label} quarter",
    "Game clock": "the {label}",
    "Game state": "plays while the team is {label}",
    "Offense personnel": "plays in {label} offensive personnel",
    "Defenders in box": "plays against a {label} defensive box",
    "Pass rushers": "plays with {label}",
    "Weather": "games with {label}",
}

GRANULARITY = {
    "total": "Season or game totals; the question does not ask for a per game or per play rate.",
    "per_game": "The question asks for an average per game.",
    "per_play": "The question asks per play, per attempt, per carry, per target, or for an "
    "efficiency rate.",
}

SEASON_REF = {
    "none": "The question names no season, or names a season by its year.",
    "this_season": "The question says this season, this year or the current season.",
    "last_season": "The question says last season or last year.",
    "two_seasons_ago": "The question says two seasons ago or two years ago.",
}
SEASON_OFFSET = {"this_season": 0, "last_season": 1, "two_seasons_ago": 2}

FIXED_QUESTIONS: dict[str, Any] = {
    "granularity": {
        "type": "choice",
        "instructions": "Does the question ask for totals, a per game average, or a per play rate?",
        "criteria": GRANULARITY,
    },
    "season_ref": {
        "type": "choice",
        "instructions": "How does the question refer to the NFL season?",
        "criteria": SEASON_REF,
    },
    "has_condition": {
        "type": "noul",
        "instructions": "Does the question limit the statistics to some situation or condition, "
        "such as a down, a quarter, a part of the field, the score, the weather, the opponent or "
        "the time left in a game? A season, a player, and per game or per play wording do not "
        "count.",
    },
    "multi_stat": {
        "type": "noul",
        "instructions": "Does the question ask for two or more different statistics?",
    },
    "leaderboard": {
        "type": "noul",
        "instructions": "Does the question ask which player or team leads or ranks highest or "
        "lowest, without naming the player or team it is about?",
    },
}


class JevError(RuntimeError):
    """Jev gave no usable answer; the caller falls back. Messages never hold the key."""


def build_jev_request(req: IntentRequest, *, model: str) -> dict[str, Any]:
    """The whole payload: the question text and questions built from the generic catalog only."""
    questions: dict[str, Any] = {}
    for s in req.stats:
        also = f" Also called: {', '.join(s.aliases)}." if s.aliases else ""
        questions[f"stat__{s.id}"] = {
            "type": "noul",
            "instructions": f"Does the question ask for the NFL statistic '{s.label}' "
            f"({s.category})?{also}",
            "criteria": {
                "true": f"The question asks for {s.label} or one of its other names.",
                "false": "The question asks for a different statistic, or none.",
            },
        }
    for f in req.filters:
        if f.group == SEASON_GROUP:
            continue
        phrase = GROUP_PHRASE.get(f.group, "{label}").format(label=f.label)
        questions[f"filter__{f.id}"] = {
            "type": "noul",
            "instructions": f"Does the question limit the statistics to {phrase} "
            f"({f.group}: {f.label})?",
        }
    return {
        "model": model,
        "state": {"question": req.question},
        "questions": questions | FIXED_QUESTIONS,
    }


def _noul(answers: dict[str, Any], key: str) -> float:
    answer = answers.get(key)
    p = answer.get("noul") if isinstance(answer, dict) else None
    if isinstance(p, bool) or not isinstance(p, int | float) or not 0 <= p <= 1:
        raise JevError(f"Jev gave no probability for {key!r}.")
    return float(p)


def _choice(answers: dict[str, Any], key: str, options: dict[str, str]) -> str:
    answer = answers.get(key)
    choice = answer.get("choice") if isinstance(answer, dict) else None
    if not isinstance(choice, str) or choice not in options:
        raise JevError(f"Jev gave no valid choice for {key!r}.")
    return str(choice)


def _unsupported(reason: str) -> UnsupportedOutcome:
    return UnsupportedOutcome(reason=reason)


def to_outcome(
    answers: dict[str, Any], req: IntentRequest, *, current_season: int
) -> IntentOutcome:
    """Design 2 of the #71 test: probabilities above THRESHOLD, seasons read in code."""
    season_ids = {f.id for f in req.filters if f.group == SEASON_GROUP}
    years = _YEAR.findall(req.question)
    if any(f"season-{y}" not in season_ids for y in years):
        return _unsupported("That season is not in the data.")
    # A ranking is a query; the client orders and cuts the rows (it refused before step 3 of the
    # 2026-11-06 Ask expansion).
    ranking = _noul(answers, "leaderboard") > THRESHOLD
    stat_p = {s.id: _noul(answers, f"stat__{s.id}") for s in req.stats}
    picked = [i for i, p in sorted(stat_p.items(), key=lambda kv: -kv[1]) if p > THRESHOLD]
    if not picked:
        return _unsupported("No stat in the catalog answers that.")
    if _noul(answers, "multi_stat") <= THRESHOLD:
        picked = picked[:1]
    filters = [
        f.id
        for f in req.filters
        if f.group != SEASON_GROUP and _noul(answers, f"filter__{f.id}") > THRESHOLD
    ]
    if _noul(answers, "has_condition") > THRESHOLD and not filters:
        return _unsupported("That condition is not one of the filters.")
    granularity = _choice(answers, "granularity", GRANULARITY)
    filters += [f"season-{y}" for y in years]
    ref = _choice(answers, "season_ref", SEASON_REF)
    if not years and ref in SEASON_OFFSET:
        season = f"season-{current_season - SEASON_OFFSET[ref]}"
        if season not in season_ids:
            return _unsupported("That season is not in the data.")
        filters.append(season)
    intent = validate_intent(
        {
            "stat_ids": picked[:MAX_INTENT_STATS],
            "filter_ids": filters,
            "granularity": granularity,
            "ranking": ranking,
        },
        stat_ids={s.id for s in req.stats},
        filter_ids={f.id for f in req.filters},
    )
    return QueryOutcome(intent=intent)


def _retry_wait(response: httpx2.Response) -> float | None:
    """Seconds to wait before retrying, or None when the wait is too long to be worth it."""
    header = response.headers.get("retry-after")
    if header is None:
        return DEFAULT_RETRY_S
    try:
        wait = float(header)
    except ValueError:
        return None  # an HTTP date: not worth parsing for a 2-second budget
    return wait if 0 <= wait <= MAX_RETRY_AFTER_S else None


async def call_jev(
    payload: dict[str, Any],
    *,
    api_key: str,
    timeout: float,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """POST (retrying once on a transport error, 429 or 5xx) and return the answers.

    `timeout` bounds the whole call, retries included, so Ask falls back without a long stall.
    """
    try:
        async with asyncio.timeout(timeout):
            return await _post_with_retry(
                payload,
                api_key=api_key,
                attempt_timeout=timeout / MAX_ATTEMPTS,
                transport=transport,
            )
    except TimeoutError as e:
        raise JevError(f"Jev took longer than {timeout:g} s.") from e


async def _post_with_retry(
    payload: dict[str, Any],
    *,
    api_key: str,
    attempt_timeout: float,
    transport: httpx2.AsyncBaseTransport | None,
) -> dict[str, Any]:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            # A fresh connection per request: reused async TLS connections failed with
            # "bad record mac" in the #71 runs.
            async with httpx2.AsyncClient(timeout=attempt_timeout, transport=transport) as client:
                response = await client.post(
                    JEV_URL, json=payload, headers={"Authorization": f"Bearer {api_key}"}
                )
        except (httpx2.TransportError, OSError) as e:  # OSError covers ssl.SSLError
            if attempt == MAX_ATTEMPTS:
                raise JevError(f"Jev request failed ({type(e).__name__}).") from e
            continue
        except httpx2.HTTPError as e:  # decoding, redirects: a retry would fail the same way
            raise JevError(f"Jev request failed ({type(e).__name__}).") from e
        if response.status_code == 429 or response.status_code >= 500:
            wait = _retry_wait(response)
            if attempt == MAX_ATTEMPTS or wait is None:
                raise JevError(f"Jev returned {response.status_code}.")
            await asyncio.sleep(wait)
            continue
        if response.status_code != 200:
            raise JevError(f"Jev returned {response.status_code}.")
        try:
            body = response.json()
        except ValueError as e:
            raise JevError("Jev returned a body that is not JSON.") from e
        answers = body.get("answers") if isinstance(body, dict) else None
        if not isinstance(answers, dict):
            raise JevError("Jev returned no answers.")
        return answers
    raise JevError("Jev was not asked.")  # unreachable: the loop returns or raises


async def translate_with_jev(
    req: IntentRequest,
    *,
    api_key: str,
    model: str,
    timeout: float,
    current_season: int | None = None,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> IntentOutcome:
    reason = undefined_term(req.question)
    if reason:  # refused in code: Jev would map the term to a near stat
        return _unsupported(reason)
    answers = await call_jev(
        build_jev_request(req, model=model), api_key=api_key, timeout=timeout, transport=transport
    )
    season = _season_now() if current_season is None else current_season
    try:
        return to_outcome(answers, req, current_season=season)
    except IntentError as e:  # cannot happen with catalog-built ids; keep it a Jev failure
        raise JevError(f"Jev outcome failed validation ({e}).") from e
