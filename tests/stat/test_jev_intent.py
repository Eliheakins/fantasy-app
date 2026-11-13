from __future__ import annotations

import asyncio
import json
import ssl
import tomllib
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fakes import FILTERS, STATS

from nfl_stat.core.config import REPO_ROOT
from nfl_stat.schemas.nlq import IntentRequest, QueryOutcome, UnsupportedOutcome
from nfl_stat.services import jev_intent
from nfl_stat.services.jev_intent import (
    JevError,
    build_jev_request,
    call_jev,
    to_outcome,
    translate_with_jev,
)

KEY = "sk-test-not-a-real-key"
EVAL_CATALOG = Path(__file__).parent / "eval" / "catalog.json"


def _req(question: str = "Mahomes passing yards in 2023") -> IntentRequest:
    return IntentRequest(question=question, stats=STATS, filters=FILTERS)


def _answers(
    stats: dict[str, float] | None = None,
    filters: dict[str, float] | None = None,
    *,
    granularity: str = "total",
    season_ref: str = "none",
    has_condition: float = 0.02,
    multi_stat: float = 0.02,
    leaderboard: float = 0.02,
) -> dict[str, Any]:
    """Jev's answers: every stat and non-season filter Noul low unless given."""
    out: dict[str, Any] = {f"stat__{s.id}": {"noul": (stats or {}).get(s.id, 0.01)} for s in STATS}
    out |= {
        f"filter__{f.id}": {"noul": (filters or {}).get(f.id, 0.01)}
        for f in FILTERS
        if f.group != "Season"
    }
    return out | {
        "granularity": {"choice": granularity},
        "season_ref": {"choice": season_ref},
        "has_condition": {"noul": has_condition},
        "multi_stat": {"noul": multi_stat},
        "leaderboard": {"noul": leaderboard},
    }


def _outcome(question: str, answers: dict[str, Any], current_season: int = 2023):
    return to_outcome(answers, _req(question), current_season=current_season)


# --- the request -----------------------------------------------------------------------------


def test_the_request_asks_a_noul_per_stat_and_non_season_filter_plus_the_fixed_questions():
    payload = build_jev_request(_req(), model="jev-latest")

    assert set(payload) == {"model", "state", "questions"}
    assert payload["model"] == "jev-latest"
    assert payload["state"] == {"question": "Mahomes passing yards in 2023"}
    questions = payload["questions"]
    assert {k for k in questions if k.startswith("stat__")} == {f"stat__{s.id}" for s in STATS}
    assert {k for k in questions if k.startswith("filter__")} == {
        "filter__stype-post",
        "filter__down-3",
    }
    assert {"granularity", "season_ref", "has_condition", "multi_stat", "leaderboard"} <= set(
        questions
    )
    assert questions["granularity"]["type"] == "choice"
    assert set(questions["granularity"]["criteria"]) == {"total", "per_game", "per_play"}
    assert "passing yards" in questions["stat__pass_yards"]["instructions"]


def test_a_request_built_from_a_question_carries_no_league_data():
    """Like the S4b check on the local path: only the question and the generic catalog leave."""
    config = tomllib.loads((REPO_ROOT / "config.toml").read_text())
    leagues = config["leagues"]
    private = [
        *leagues,
        *(cfg["id"] for cfg in leagues.values()),
        config["user_id"],
        "Lisan Al-Caleb",
        "LaPorta Potty",
    ]
    catalog = json.loads(EVAL_CATALOG.read_text())
    # A client that tries to send league or roster data has it dropped by the request schema.
    req = IntentRequest.model_validate(
        {
            "question": "Bijan fantasy points in 2023",
            **catalog,
            "league": leagues["colgate"]["id"],
            "roster": ["Lisan Al-Caleb"],
        }
    )

    body = json.dumps(build_jev_request(req, model="jev-latest"))

    assert json.loads(body)["state"] == {"question": "Bijan fantasy points in 2023"}
    for value in private:
        assert value.lower() not in body.lower(), value


# --- answers to an outcome -------------------------------------------------------------------


def test_a_stat_with_an_explicit_year_becomes_a_query():
    outcome = _outcome("Mahomes passing yards in 2023", _answers({"pass_yards": 0.97}))

    assert outcome == QueryOutcome.model_validate(
        {
            "intent": {
                "stat_ids": ["pass_yards"],
                "filter_ids": ["season-2023"],
                "granularity": "total",
            }
        }
    )


def test_only_the_top_stat_is_kept_unless_the_question_asks_for_several():
    answers = _answers({"pass_yards": 0.7, "pass_tds": 0.9})

    one = _outcome("Mahomes passing in 2023", answers)
    both = _outcome("Mahomes passing in 2023", answers | {"multi_stat": {"noul": 0.9}})

    assert isinstance(one, QueryOutcome) and one.intent.stat_ids == ["pass_tds"]
    assert isinstance(both, QueryOutcome) and both.intent.stat_ids == ["pass_tds", "pass_yards"]


def test_filters_and_granularity_above_the_threshold_are_used():
    answers = _answers(
        {"eff_epa": 0.95},
        {"down-3": 0.8, "stype-post": 0.5},
        granularity="per_play",
        has_condition=0.9,
    )

    outcome = _outcome("Allen EPA per play on third down", answers)

    assert isinstance(outcome, QueryOutcome)
    assert outcome.intent.filter_ids == ["down-3"]
    assert outcome.intent.granularity == "per_play"


@pytest.mark.parametrize(
    ("question", "answers"),
    [
        ("Mahomes salary in 2023", _answers()),
        (
            "Mahomes passing yards against the Chiefs in 2023",
            _answers({"pass_yards": 0.9}, has_condition=0.9),
        ),
        ("Mahomes passing yards in 2019", _answers({"pass_yards": 0.99})),
    ],
    ids=["no stat", "condition with no filter", "season outside the data"],
)
def test_questions_the_catalog_cannot_answer_are_unsupported(question: str, answers: dict):
    outcome = _outcome(question, answers)

    assert isinstance(outcome, UnsupportedOutcome)
    assert outcome.reason


def test_a_ranking_is_a_query_that_says_it_ranks():
    ranked = _outcome(
        "Who led the league in passing yards in 2023",
        _answers({"pass_yards": 0.9}, leaderboard=0.8),
    )
    plain = _outcome("Mahomes passing yards in 2023", _answers({"pass_yards": 0.9}))

    assert isinstance(ranked, QueryOutcome) and ranked.intent.ranking is True
    assert ranked.intent.stat_ids == ["pass_yards"]
    assert isinstance(plain, QueryOutcome) and plain.intent.ranking is False


def test_a_relative_season_is_turned_into_a_year_from_the_current_season():
    answers = _answers({"pass_yards": 0.9}, season_ref="last_season")

    last = _outcome("Mahomes passing yards last season", answers, current_season=2023)
    too_old = _outcome("Mahomes passing yards last season", answers, current_season=2022)
    explicit = _outcome("Mahomes passing yards in 2023", answers, current_season=2026)

    assert isinstance(last, QueryOutcome) and last.intent.filter_ids == ["season-2022"]
    assert isinstance(too_old, UnsupportedOutcome)
    # An explicit year wins over the relative choice.
    assert isinstance(explicit, QueryOutcome) and explicit.intent.filter_ids == ["season-2023"]


def test_at_most_five_stats_are_kept():
    stats = {s.id: 0.9 for s in STATS} | {"pass_yards": 0.99}
    many = [*STATS, *(STATS[0].model_copy(update={"id": f"x{i}"}) for i in range(3))]
    req = IntentRequest(question="everything", stats=many, filters=FILTERS)
    answers = _answers(stats, multi_stat=0.9) | {f"stat__x{i}": {"noul": 0.9} for i in range(3)}

    outcome = to_outcome(answers, req, current_season=2023)

    assert isinstance(outcome, QueryOutcome)
    assert len(outcome.intent.stat_ids) == 5
    assert outcome.intent.stat_ids[0] == "pass_yards"


@pytest.mark.parametrize(
    "broken",
    [
        {"stat__pass_yards": {"noul": "high"}},
        {"stat__pass_yards": {}},
        {"leaderboard": None},
        {"granularity": {"choice": "weekly"}},
        {"granularity": {"choice": ["total"]}},
    ],
    ids=["text probability", "missing probability", "missing answer", "unknown choice", "list"],
)
def test_a_malformed_answer_is_a_jev_error(broken: dict[str, Any]):
    with pytest.raises(JevError):
        _outcome("Mahomes passing yards in 2023", _answers({"pass_yards": 0.9}) | broken)


# --- the HTTP call ---------------------------------------------------------------------------


def _transport(*responses: httpx2.Response | Exception) -> tuple[httpx2.MockTransport, list]:
    seen: list[httpx2.Request] = []
    queue = list(responses)

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return httpx2.MockTransport(handle), seen


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    waited: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waited.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return waited


async def _call(transport: httpx2.MockTransport) -> dict[str, Any]:
    return await call_jev({"questions": {}}, api_key=KEY, timeout=1.0, transport=transport)


async def test_a_good_reply_returns_the_answers_and_sends_the_bearer_key(sleeps):
    transport, seen = _transport(httpx2.Response(200, json={"answers": {"a": {"noul": 0.5}}}))

    assert await _call(transport) == {"a": {"noul": 0.5}}
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"
    assert str(seen[0].url) == jev_intent.JEV_URL


@pytest.mark.parametrize(
    "error",
    [httpx2.ConnectError("refused"), ssl.SSLError("bad record mac"), httpx2.ReadTimeout("slow")],
    ids=["network", "tls", "timeout"],
)
async def test_a_transport_error_is_retried_once(sleeps, error: Exception):
    transport, seen = _transport(error, httpx2.Response(200, json={"answers": {}}))

    assert await _call(transport) == {}
    assert len(seen) == 2


async def test_two_transport_errors_are_a_jev_error(sleeps):
    transport, _ = _transport(ssl.SSLError("bad record mac"), ssl.SSLError("bad record mac"))

    with pytest.raises(JevError):
        await _call(transport)


async def test_a_429_waits_for_retry_after_then_retries(sleeps):
    transport, seen = _transport(
        httpx2.Response(429, headers={"retry-after": "1"}),
        httpx2.Response(200, json={"answers": {}}),
    )

    assert await _call(transport) == {}
    assert sleeps == [1.0] and len(seen) == 2


async def test_a_429_asking_for_a_long_wait_gives_up_at_once(sleeps):
    transport, seen = _transport(httpx2.Response(429, headers={"retry-after": "60"}))

    with pytest.raises(JevError):
        await _call(transport)
    assert sleeps == [] and len(seen) == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(401, json={"error": f"bad key {KEY}"}),
        httpx2.Response(200, text="not json"),
        httpx2.Response(200, json={"no": "answers"}),
    ],
    ids=["4xx", "not json", "no answers"],
)
async def test_a_bad_reply_is_a_jev_error_without_a_retry_and_without_the_key(sleeps, response):
    transport, seen = _transport(response)

    with pytest.raises(JevError) as err:
        await _call(transport)
    assert len(seen) == 1
    assert KEY not in str(err.value)


async def test_a_5xx_is_retried_once_then_a_jev_error(sleeps):
    transport, seen = _transport(httpx2.Response(503), httpx2.Response(502))

    with pytest.raises(JevError, match="502"):
        await _call(transport)
    assert len(seen) == 2


async def test_translate_with_jev_sends_the_request_and_maps_the_answers(sleeps):
    replies: list[dict[str, Any]] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        replies.append(json.loads(request.content))
        return httpx2.Response(200, json={"answers": _answers({"pass_yards": 0.9})})

    outcome = await translate_with_jev(
        _req(),
        api_key=KEY,
        model="jev-x",
        timeout=1.0,
        current_season=2023,
        transport=httpx2.MockTransport(handle),
    )

    assert isinstance(outcome, QueryOutcome)
    assert outcome.intent.stat_ids == ["pass_yards"]
    assert replies[0]["model"] == "jev-x"


async def test_a_decoding_error_is_a_jev_error_without_a_retry(sleeps):
    transport, seen = _transport(httpx2.DecodingError("bad gzip"))

    with pytest.raises(JevError, match="DecodingError"):
        await _call(transport)
    assert len(seen) == 1


async def test_each_attempt_opens_a_fresh_client(sleeps, monkeypatch: pytest.MonkeyPatch):
    opened: list[httpx2.AsyncClient] = []
    real = httpx2.AsyncClient

    def tracking(*args: Any, **kwargs: Any) -> httpx2.AsyncClient:
        opened.append(real(*args, **kwargs))
        return opened[-1]

    monkeypatch.setattr(httpx2, "AsyncClient", tracking)
    transport, _ = _transport(httpx2.ConnectError("x"), httpx2.Response(200, json={"answers": {}}))

    await _call(transport)

    assert len(opened) == 2 and opened[0] is not opened[1]


async def test_the_timeout_bounds_the_whole_call_including_retries():
    async def slow(request: httpx2.Request) -> httpx2.Response:
        await asyncio.sleep(1)
        return httpx2.Response(200, json={"answers": {}})

    with pytest.raises(JevError, match="longer than"):
        await call_jev({}, api_key=KEY, timeout=0.05, transport=httpx2.MockTransport(slow))
