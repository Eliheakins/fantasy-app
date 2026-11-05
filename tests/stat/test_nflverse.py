"""Both halves fetch player stats and rosters through nfl_stat.pipeline.nflverse, with the same
arguments they used before it existed. No network: nflreadpy is replaced by a recording fake."""

from pathlib import Path
from typing import Any

import polars as pl
import pytest

from fantasy.stages import ingest_nfl, ingest_role
from nfl_stat.pipeline import nfl_pipeline, nflverse, player_game


class FakeNflreadpy:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        def loader(*args: Any, **kwargs: Any) -> pl.DataFrame:
            self.calls.append((name, args, kwargs))
            return pl.DataFrame({"gsis_id": ["g"]})

        return loader


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeNflreadpy:
    fake = FakeNflreadpy()
    monkeypatch.setattr(nflverse, "nfl", fake)
    monkeypatch.setattr(ingest_role, "seasons", lambda: [2024, 2025])
    return fake


def test_fantasy_player_stats_ask_for_every_configured_season_by_week(fake: FakeNflreadpy):
    loader, _ = ingest_nfl.SOURCES["nfl_player_stats"]

    loader()

    assert fake.calls == [("load_player_stats", ([2024, 2025],), {"summary_level": "week"})]


def test_stat_player_game_asks_for_the_requested_seasons_by_week(
    fake: FakeNflreadpy, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(player_game, "normalize_player_game", lambda df: df)

    player_game.build_player_game([2023])

    assert fake.calls == [("load_player_stats", ([2023],), {"summary_level": "week"})]


def test_fantasy_rosters_are_the_weekly_file(fake: FakeNflreadpy, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ingest_role, "roster_features", lambda df: df)

    ingest_role.load_rosters()

    assert fake.calls == [("load_rosters_weekly", ([2024, 2025],), {})]


def test_stat_player_index_asks_for_the_season_rosters(
    fake: FakeNflreadpy, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # The fake's one-column frame stops create_player_index right after the fetch.
    with pytest.raises(pl.exceptions.ColumnNotFoundError):
        nfl_pipeline.create_player_index(tmp_path, [2023])

    assert fake.calls == [("load_rosters", ([2023],), {})]
