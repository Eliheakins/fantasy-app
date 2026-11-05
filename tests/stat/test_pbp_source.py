from __future__ import annotations

import os
import time
from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

from fantasy.stages import environment, ingest_role
from nfl_stat.pipeline import pbp_source

CURRENT = 2026
DAY = 24 * 3600


class Fetcher:
    """Stands in for the network: writes a small parquet and counts the calls."""

    def __init__(self) -> None:
        self.calls: list[int] = []

    def __call__(self, season: int, dest: Path) -> None:
        self.calls.append(season)
        pl.DataFrame({"season": [season], "epa": [0.5], "play_id": [1]}).write_parquet(dest)


@pytest.fixture
def fetch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Fetcher:
    fetcher = Fetcher()
    monkeypatch.setattr(pbp_source, "PBP_DIR", tmp_path / "pbp")
    monkeypatch.setattr(pbp_source, "_fetch", fetcher)
    monkeypatch.setattr(pbp_source, "get_current_season", lambda: CURRENT)
    return fetcher


def age(path: Path, hours: float) -> None:
    old = time.time() - hours * 3600
    os.utime(path, (old, old))


def test_cache_path_is_one_file_per_season(fetch: Fetcher, tmp_path: Path):
    path = pbp_source.ensure_pbp(2024)

    assert path == tmp_path / "pbp" / "2024.parquet"
    assert path.exists()
    assert pbp_source.pbp_path(2025) == tmp_path / "pbp" / "2025.parquet"


def test_completed_season_is_never_refetched(fetch: Fetcher):
    path = pbp_source.ensure_pbp(2024)
    age(path, 365 * 24)

    pbp_source.ensure_pbp(2024)

    assert fetch.calls == [2024]


def test_current_season_is_reused_inside_the_ttl(fetch: Fetcher):
    path = pbp_source.ensure_pbp(CURRENT)
    age(path, pbp_source.TTL_HOURS - 1)

    pbp_source.ensure_pbp(CURRENT)

    assert fetch.calls == [CURRENT]


def test_current_season_is_refetched_after_the_ttl(fetch: Fetcher):
    path = pbp_source.ensure_pbp(CURRENT)
    age(path, pbp_source.TTL_HOURS + 1)

    pbp_source.ensure_pbp(CURRENT)

    assert fetch.calls == [CURRENT, CURRENT]


def stamp(path: Path, when: datetime) -> None:
    os.utime(path, (when.timestamp(), when.timestamp()))


def test_completed_season_fetched_mid_season_is_refetched_once(fetch: Fetcher):
    path = pbp_source.ensure_pbp(2024)
    stamp(path, datetime(2024, 11, 20))  # fetched before the season's last weeks

    pbp_source.ensure_pbp(2024)
    pbp_source.ensure_pbp(2024)

    assert fetch.calls == [2024, 2024]


def test_completed_season_fetched_after_it_ended_is_kept(fetch: Fetcher):
    path = pbp_source.ensure_pbp(2024)
    stamp(path, datetime(2025, 3, 1))

    pbp_source.ensure_pbp(2024)

    assert fetch.calls == [2024]


def test_future_modified_time_is_not_fresh_forever(fetch: Fetcher):
    path = pbp_source.ensure_pbp(CURRENT)
    age(path, -48)

    pbp_source.ensure_pbp(CURRENT)

    assert fetch.calls == [CURRENT, CURRENT]


def test_corrupt_download_is_not_cached(fetch: Fetcher, monkeypatch: pytest.MonkeyPatch):
    def corrupt(season: int, dest: Path) -> None:
        dest.write_bytes(b"<html>rate limited</html>")

    monkeypatch.setattr(pbp_source, "_fetch", corrupt)

    with pytest.raises(ValueError, match="parquet"):
        pbp_source.ensure_pbp(2024)

    assert list(pbp_source.PBP_DIR.iterdir()) == []


def test_corrupt_refresh_keeps_the_old_file(fetch: Fetcher, monkeypatch: pytest.MonkeyPatch):
    path = pbp_source.ensure_pbp(CURRENT)
    age(path, pbp_source.TTL_HOURS + 1)
    before = path.read_bytes()
    monkeypatch.setattr(pbp_source, "_fetch", lambda season, dest: dest.write_bytes(b"junk"))

    with pytest.raises(ValueError):
        pbp_source.ensure_pbp(CURRENT)

    assert path.read_bytes() == before


def test_columns_are_selected_when_asked(fetch: Fetcher):
    assert pbp_source.read_pbp(2024, columns=["epa"]).columns == ["epa"]


def test_failed_download_leaves_no_file(fetch: Fetcher, monkeypatch: pytest.MonkeyPatch):
    def broken(season: int, dest: Path) -> None:
        dest.write_bytes(b"PAR1 half a file")
        raise ConnectionError("dropped")

    monkeypatch.setattr(pbp_source, "_fetch", broken)

    with pytest.raises(ConnectionError):
        pbp_source.ensure_pbp(2024)

    assert list((pbp_source.PBP_DIR).iterdir()) == []


def test_failed_refresh_keeps_the_old_file(fetch: Fetcher, monkeypatch: pytest.MonkeyPatch):
    path = pbp_source.ensure_pbp(CURRENT)
    age(path, pbp_source.TTL_HOURS + 1)
    before = path.read_bytes()

    def broken(season: int, dest: Path) -> None:
        raise ConnectionError("dropped")

    monkeypatch.setattr(pbp_source, "_fetch", broken)
    with pytest.raises(ConnectionError):
        pbp_source.ensure_pbp(CURRENT)

    assert path.read_bytes() == before


def test_season_past_the_clock_raises_nflreadpys_message(fetch: Fetcher):
    with pytest.raises(ValueError, match="Season must be between"):
        pbp_source.ensure_pbp(CURRENT + 1)

    assert fetch.calls == []


class _Response:
    status_code = 404


class _NotFound(Exception):
    response = _Response()


def _pace_frame(season: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "season": [season, season],
            "week": [1, 1],
            "season_type": ["REG", "REG"],
            "pass": [1, 0],
            "rush": [0, 1],
            "posteam": ["AAA", "AAA"],
            "qb_dropback": [1, 0],
            "pass_oe": [2.0, None],
            "epa": [0.25, 0.75],
        }
    )


def test_unpublished_current_season_is_skipped_with_the_same_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr(ingest_role, "seasons", lambda: [2024, 2025])

    def read(season: int, columns: list[str] | None = None) -> pl.DataFrame:
        if season == 2025:
            raise ConnectionError("Failed to download") from _NotFound()
        return _pace_frame(season).select(columns)

    monkeypatch.setattr(ingest_role, "read_pbp", read)

    out = ingest_role.load_pace()

    assert out["season"].unique().to_list() == [2024]
    assert "team pace: 2025 is not published yet, skipping it" in capsys.readouterr().out


def test_unpublished_earlier_season_still_stops_the_run(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ingest_role, "seasons", lambda: [2024, 2025])

    def read(season: int, columns: list[str] | None = None) -> pl.DataFrame:
        if season == 2024:
            raise ConnectionError("Failed to download") from _NotFound()
        return _pace_frame(season).select(columns)

    monkeypatch.setattr(ingest_role, "read_pbp", read)

    with pytest.raises(ConnectionError):
        ingest_role.load_pace()


def test_pace_and_efficiency_read_only_the_columns_they_use(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, list[str] | None] = {}
    full = _pace_frame(2024).with_columns(defteam=pl.lit("BBB"), sack=pl.lit(0.0), junk=pl.lit(1))

    def reader(name: str):
        def read(season: int, columns: list[str] | None = None) -> pl.DataFrame:
            seen[name] = columns
            assert columns is not None
            return full.select(columns)  # a column the reader forgot to ask for would raise

        return read

    monkeypatch.setattr(ingest_role, "seasons", lambda: [2024])
    monkeypatch.setattr(ingest_role, "read_pbp", reader("pace"))
    monkeypatch.setattr(environment, "read_pbp", reader("eff"))

    assert ingest_role.load_pace().height == 1
    assert environment.team_efficiency(range(2024, 2025)).height == 1
    assert seen["pace"] and seen["eff"]
    assert "junk" not in (seen["pace"] or []) + (seen["eff"] or [])
