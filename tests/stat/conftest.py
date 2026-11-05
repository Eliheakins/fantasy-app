from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from nfl_stat.api.deps import get_llm_client
from nfl_stat.main import create_app
from nfl_stat.schemas.nlq import CatalogFilter, CatalogStat

STATS = [
    CatalogStat(
        id="pass_yards",
        label="Pass yards",
        category="passing",
        aliases=["passing yards", "yards through the air"],
    ),
    CatalogStat(id="pass_tds", label="Pass TDs", category="passing"),
    CatalogStat(id="rec_yards", label="Rec yards", category="receiving"),
    CatalogStat(id="rec_receptions", label="Receptions", category="receiving"),
    CatalogStat(id="eff_epa", label="EPA/Play", category="efficiency"),
]
FILTERS = [
    CatalogFilter(id="season-2023", label="2023", group="Season"),
    CatalogFilter(id="season-2022", label="2022", group="Season"),
    CatalogFilter(id="stype-post", label="Playoffs", group="Season type"),
    CatalogFilter(id="down-3", label="3rd", group="Down"),
]


class FakeLlm:
    """Stands in for AsyncOpenAI: returns scripted replies and records the messages it saw."""

    def __init__(self, replies: list[str]) -> None:
        self._replies = list(replies)
        self.calls: list[list[dict[str, Any]]] = []
        self.base_url = "http://fake-llm/v1"
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, *, messages: list[dict[str, Any]], **_: Any) -> Any:
        self.calls.append(messages)
        content = self._replies.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """The folder the app under test reads its data from; empty until a test builds something."""
    return tmp_path


@pytest.fixture
def app(data_dir: Path) -> Iterator[FastAPI]:
    # Each test gets its own settings and state, so nothing leaks between tests.
    yield create_app(
        SimpleNamespace(
            data_dir=data_dir,
            llm_model="test-model",
            llm_base_url="http://fake-llm/v1",
            llm_timeout_seconds=1.0,
            intent_provider="local",
            jev_api_key=None,
            jev_model="jev-latest",
            jev_timeout_seconds=1.0,
        )
    )


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def use_llm(app: FastAPI) -> Callable[[list[str]], FakeLlm]:
    def _use(replies: list[str]) -> FakeLlm:
        fake = FakeLlm(replies)
        app.dependency_overrides[get_llm_client] = lambda: fake
        return fake

    return _use
