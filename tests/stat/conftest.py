from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import httpx2
import pytest
from fakes import FakeLlm
from fastapi import FastAPI

from nfl_stat.api.deps import get_llm_client
from nfl_stat.core.config import AppSettings
from nfl_stat.main import create_app


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    """The folder the app under test reads its data from; empty until a test builds something."""
    return tmp_path


@pytest.fixture
def app(data_dir: Path) -> Iterator[FastAPI]:
    # Each test gets its own settings and state, so nothing leaks between tests.
    yield create_app(
        AppSettings(
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
async def client(app: FastAPI) -> AsyncIterator[httpx2.AsyncClient]:
    transport = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def use_llm(app: FastAPI) -> Callable[[list[str]], FakeLlm]:
    def _use(replies: list[str]) -> FakeLlm:
        fake = FakeLlm(replies)
        app.dependency_overrides[get_llm_client] = lambda: fake
        return fake

    return _use
