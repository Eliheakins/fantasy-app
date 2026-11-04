from __future__ import annotations

import httpx
import openai
import pytest
from conftest import FILTERS, STATS

from api.deps import get_llm_client
from core.state import app_state
from schemas.manifest import JsonFileEntry, Manifest, SeasonEntry
from services.llm_client import chat_text


def _intent_body(question: str = "Mahomes passing yards in 2023") -> dict:
    return {
        "question": question,
        "stats": [s.model_dump() for s in STATS],
        "filters": [f.model_dump() for f in FILTERS],
    }


async def test_health_is_degraded_until_the_data_is_built(client: httpx.AsyncClient):
    res = await client.get("/health")

    assert res.status_code == 200
    assert res.json() == {
        "status": "degraded",
        "data_ready": False,
        "data_through": None,
        "seasons": [],
    }


async def test_health_reports_how_current_the_data_is(client: httpx.AsyncClient):
    app_state.manifest = Manifest(
        built_at="2026-11-04T12:00:00+00:00",
        nflreadpy_version="1",
        seasons=[
            SeasonEntry(
                season=2025,
                path="nfl_pbp_2025.parquet",
                rows=1,
                max_week=22,
                has_participation=True,
            ),
            SeasonEntry(
                season=2026,
                path="nfl_pbp_2026.parquet",
                rows=1,
                max_week=9,
                has_participation=False,
            ),
        ],
    )

    app_state.manifest = app_state.manifest.model_copy(
        update={"players": JsonFileEntry(path="players.json", rows=1)}
    )

    body = (await client.get("/health")).json()

    assert body["status"] == "ok"
    assert body["data_ready"] is True
    assert body["data_through"] == "2026 week 9"
    assert body["seasons"] == [2025, 2026]


async def test_the_player_and_shard_endpoints_are_gone_because_the_data_is_static(
    client: httpx.AsyncClient,
):
    for path in ("/search?q=a", "/players/dictionary", "/player/00-0033873", "/pbp/shards"):
        assert (await client.get(path)).status_code == 404, path


async def test_nlq_intent_returns_validated_intent(client: httpx.AsyncClient, use_llm):
    use_llm(['{"stat_ids": ["pass_yards"], "filter_ids": ["season-2023"], "granularity": "total"}'])

    res = await client.post("/nlq/intent", json=_intent_body())

    assert res.status_code == 200
    assert res.json() == {
        "outcome": "query",
        "intent": {
            "stat_ids": ["pass_yards"],
            "filter_ids": ["season-2023"],
            "granularity": "total",
        },
    }


async def test_nlq_intent_returns_the_reason_when_the_question_is_unsupported(
    client: httpx.AsyncClient, use_llm
):
    use_llm(['{"unsupported": "Salaries are not in the play-by-play data."}'])

    res = await client.post("/nlq/intent", json=_intent_body("Mahomes salary in 2023"))

    assert res.status_code == 200
    assert res.json() == {
        "outcome": "unsupported",
        "reason": "Salaries are not in the play-by-play data.",
    }


async def test_nlq_intent_returns_422_when_model_never_produces_valid_json(
    client: httpx.AsyncClient, use_llm
):
    use_llm(["nope", "still nope"])

    res = await client.post("/nlq/intent", json=_intent_body())

    assert res.status_code == 422
    assert "couldn't turn that into a query" in res.json()["detail"]


async def test_nlq_intent_rejects_empty_question(client: httpx.AsyncClient, use_llm):
    use_llm([])

    res = await client.post("/nlq/intent", json=_intent_body(question=""))

    assert res.status_code == 422


async def test_nlq_intent_returns_503_when_llm_server_is_down(client: httpx.AsyncClient, app):
    class DownLlm:
        base_url = "http://127.0.0.1:8080/v1"

        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**_):
                    raise openai.APIConnectionError(
                        request=httpx.Request("POST", "http://127.0.0.1:8080/v1/chat/completions")
                    )

    app.dependency_overrides[get_llm_client] = lambda: DownLlm()

    res = await client.post("/nlq/intent", json=_intent_body())

    assert res.status_code == 503
    assert "mlx_lm.server" in res.json()["detail"]


async def test_chat_text_raises_502_when_model_returns_no_choices():
    class EmptyLlm:
        base_url = "http://fake/v1"

        class chat:  # noqa: N801
            class completions:  # noqa: N801
                @staticmethod
                async def create(**_):
                    return type("R", (), {"choices": []})()

    with pytest.raises(Exception) as exc:
        await chat_text(client=EmptyLlm(), model="m", messages=[])

    assert getattr(exc.value, "status_code", None) == 502


async def test_health_is_degraded_when_seasons_exist_but_the_players_file_does_not(
    client: httpx.AsyncClient,
):
    app_state.manifest = Manifest(
        built_at="2026-11-04T12:00:00+00:00",
        nflreadpy_version="1",
        seasons=[
            SeasonEntry(
                season=2026, path="nfl_pbp_2026.parquet", rows=1, max_week=9, has_participation=True
            )
        ],
    )

    body = (await client.get("/health")).json()

    assert body["status"] == "degraded"
    assert body["data_ready"] is False
    assert body["seasons"] == [2026]
