from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest
from conftest import FILTERS, STATS, FakeLlm
from fastapi import HTTPException
from pydantic import SecretStr

from nfl_stat.schemas.nlq import IntentRequest, QueryOutcome, UnsupportedOutcome
from nfl_stat.services import intent_provider
from nfl_stat.services.intent_provider import answer_intent
from nfl_stat.services.jev_intent import JevError

KEY = "sk-test-not-a-real-key"
LOCAL_REPLY = '{"stat_ids": ["rec_yards"], "granularity": "total"}'
JEV_OUTCOME = UnsupportedOutcome(reason="from jev")


def _settings(provider: str, key: str | None = KEY) -> SimpleNamespace:
    return SimpleNamespace(
        intent_provider=provider,
        jev_api_key=SecretStr(key) if key is not None else None,
        jev_model="jev-latest",
        jev_timeout_seconds=1.0,
        llm_model="local-model",
    )


def _req() -> IntentRequest:
    return IntentRequest(question="Kelce receiving yards", stats=STATS, filters=FILTERS)


@pytest.fixture
def jev(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Replaces the Jev call; set `error` to make it fail."""
    state = SimpleNamespace(calls=[], error=None)

    async def fake(req: IntentRequest, **kwargs: Any) -> Any:
        state.calls.append(kwargs)
        if state.error:
            raise state.error
        return JEV_OUTCOME

    monkeypatch.setattr(intent_provider, "translate_with_jev", fake)
    return state


async def test_local_never_calls_jev_even_with_a_key(jev):
    llm = FakeLlm([LOCAL_REPLY])

    outcome = await answer_intent(_req(), settings=_settings("local"), llm_client=llm)

    assert isinstance(outcome, QueryOutcome)
    assert jev.calls == []


@pytest.mark.parametrize("provider", ["auto", "jev"])
async def test_jev_answers_when_a_key_is_set(jev, provider: str):
    llm = FakeLlm([])

    outcome = await answer_intent(_req(), settings=_settings(provider), llm_client=llm)

    assert outcome == JEV_OUTCOME
    assert jev.calls == [{"api_key": KEY, "model": "jev-latest", "timeout": 1.0}]
    assert llm.calls == []


@pytest.mark.parametrize("key", [None, ""])
@pytest.mark.parametrize("provider", ["auto", "jev"])
async def test_no_key_uses_the_local_model(jev, provider: str, key: str | None):
    llm = FakeLlm([LOCAL_REPLY])

    outcome = await answer_intent(_req(), settings=_settings(provider, key), llm_client=llm)

    assert isinstance(outcome, QueryOutcome)
    assert jev.calls == []


async def test_a_jev_failure_falls_back_to_the_local_model_and_never_logs_the_key(
    jev, caplog: pytest.LogCaptureFixture
):
    jev.error = JevError("Jev returned 503")
    llm = FakeLlm([LOCAL_REPLY])

    with caplog.at_level(logging.DEBUG):
        outcome = await answer_intent(_req(), settings=_settings("auto"), llm_client=llm)

    assert isinstance(outcome, QueryOutcome)
    assert len(llm.calls) == 1
    assert "falling back" in caplog.text
    assert KEY not in caplog.text


async def test_a_jev_failure_with_the_local_server_down_is_the_model_unavailable_error(jev):
    jev.error = JevError("Jev request failed (ConnectError)")

    base_url = "http://127.0.0.1:8080/v1"

    async def refuse(**_: Any) -> Any:
        raise openai.APIConnectionError(request=httpx.Request("POST", base_url))

    down = SimpleNamespace(
        base_url=base_url, chat=SimpleNamespace(completions=SimpleNamespace(create=refuse))
    )

    with pytest.raises(HTTPException) as err:
        await answer_intent(_req(), settings=_settings("jev"), llm_client=down)

    assert err.value.status_code == 503


async def test_the_endpoint_falls_back_to_the_local_model_when_jev_fails(
    jev, app, client: httpx.AsyncClient, use_llm
):
    jev.error = JevError("Jev returned 500")
    app.state.stat_settings = _settings("jev")
    llm = use_llm([LOCAL_REPLY])

    res = await client.post(
        "/api/stat/nlq/intent",
        json={
            "question": "Kelce receiving yards",
            "stats": [s.model_dump() for s in STATS],
            "filters": [f.model_dump() for f in FILTERS],
        },
    )

    assert res.status_code == 200
    assert res.json()["intent"]["stat_ids"] == ["rec_yards"]
    assert len(jev.calls) == 1 and len(llm.calls) == 1
