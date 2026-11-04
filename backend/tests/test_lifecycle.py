from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import polars as pl
import pytest
from fastapi import FastAPI

from core import lifecycle, manifest_state
from core.state import app_state
from pipeline.manifest import build_manifest, write_manifest


def _write_shard(data_dir: Path) -> None:
    pl.DataFrame(
        {"season": [2026], "week": [9], "season_type": ["REG"], "defenders_in_box": [None]},
        schema_overrides={"defenders_in_box": pl.Int32},
    ).write_parquet(data_dir / "nfl_pbp_2026.parquet")


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[SimpleNamespace]:
    fake = SimpleNamespace(
        data_dir=tmp_path,
        # Port 9 refuses connections, so the keep-alive ping fails fast and is ignored.
        llm_base_url="http://127.0.0.1:9/v1",
        llm_model="m",
        llm_timeout_seconds=1.0,
    )
    monkeypatch.setattr(lifecycle, "get_settings", lambda: fake)
    yield fake
    app_state.manifest = None
    app_state.llm_client = None


async def test_lifespan_starts_the_llm_client_and_closes_it(settings: SimpleNamespace):
    async with lifecycle.lifespan(FastAPI()):
        assert app_state.llm_client is not None

    assert app_state.llm_client is None


async def test_lifespan_loads_the_manifest_when_one_was_built(settings: SimpleNamespace):
    _write_shard(settings.data_dir)
    write_manifest(build_manifest(settings.data_dir), settings.data_dir)

    async with lifecycle.lifespan(FastAPI()):
        assert app_state.manifest is not None
        assert app_state.manifest.data_through == "2026 week 9"


async def test_lifespan_starts_without_a_manifest_when_the_file_is_invalid(
    settings: SimpleNamespace,
):
    (settings.data_dir / "manifest.json").write_text("{not json")

    async with lifecycle.lifespan(FastAPI()):
        assert app_state.manifest is None
        assert app_state.llm_client is not None


async def test_lifespan_starts_when_the_manifest_cannot_be_read_at_all(
    settings: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
):
    def unreadable(data_dir: Path):
        raise PermissionError("denied")

    monkeypatch.setattr(manifest_state, "read_manifest", unreadable)

    async with lifecycle.lifespan(FastAPI()):
        assert app_state.manifest is None
        assert app_state.llm_client is not None
