from __future__ import annotations

from pathlib import Path

import httpx
import openai
import pytest
from conftest import FILTERS, STATS

from nfl_stat.api.deps import get_llm_client
from nfl_stat.pipeline.manifest import write_manifest
from nfl_stat.schemas.manifest import JsonFileEntry, Manifest, SeasonEntry
from nfl_stat.services.llm_client import chat_text


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


def _manifest(
    *, week: int, seasons: tuple[int, ...] = (2025, 2026), players: bool = True
) -> Manifest:
    return Manifest(
        built_at="2026-11-04T12:00:00+00:00",
        nflreadpy_version="1",
        seasons=[
            SeasonEntry(
                season=season,
                path=f"nfl_pbp_{season}.parquet",
                rows=1,
                max_week=week if season == seasons[-1] else 22,
                has_participation=True,
            )
            for season in seasons
        ],
        players=JsonFileEntry(path="players.json", rows=1) if players else None,
    )


async def test_health_reports_how_current_the_data_is(client: httpx.AsyncClient, data_dir: Path):
    write_manifest(_manifest(week=9), data_dir)

    body = (await client.get("/health")).json()

    assert body["status"] == "ok"
    assert body["data_ready"] is True
    assert body["data_through"] == "2026 week 9"
    assert body["seasons"] == [2025, 2026]


async def test_health_follows_a_rebuild_without_restarting_the_api(
    client: httpx.AsyncClient, data_dir: Path
):
    write_manifest(_manifest(week=9), data_dir)
    assert (await client.get("/health")).json()["data_through"] == "2026 week 9"

    write_manifest(_manifest(week=10, seasons=(2025, 2026, 2027)), data_dir)
    body = (await client.get("/health")).json()

    assert body["data_through"] == "2027 week 10"
    assert body["seasons"] == [2025, 2026, 2027]


async def test_health_goes_degraded_when_the_manifest_disappears(
    client: httpx.AsyncClient, data_dir: Path
):
    write_manifest(_manifest(week=9), data_dir)
    assert (await client.get("/health")).json()["status"] == "ok"

    (data_dir / "manifest.json").unlink()

    assert (await client.get("/health")).json()["status"] == "degraded"


async def test_health_reports_a_broken_manifest_instead_of_failing(
    client: httpx.AsyncClient, data_dir: Path
):
    (data_dir / "manifest.json").write_text("{not json")

    res = await client.get("/health")

    assert res.status_code == 200
    assert res.json()["status"] == "degraded"


async def test_health_is_degraded_when_seasons_exist_but_the_players_file_does_not(
    client: httpx.AsyncClient, data_dir: Path
):
    write_manifest(_manifest(week=9, seasons=(2026,), players=False), data_dir)

    body = (await client.get("/health")).json()

    assert body["status"] == "degraded"
    assert body["data_ready"] is False
    assert body["seasons"] == [2026]


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
