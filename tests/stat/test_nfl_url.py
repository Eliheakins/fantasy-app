from __future__ import annotations

import pytest

from nfl_stat.pipeline.pbp_source import get_nfl_url


def test_default_url_points_at_the_nflverse_release(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("NFLVERSE_DOWNLOAD_BASE", raising=False)

    assert get_nfl_url(2026, "pbp") == (
        "https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_2026.parquet"
    )


def test_a_local_mirror_over_http_is_allowed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NFLVERSE_DOWNLOAD_BASE", "http://localhost:9000/mirror")

    assert get_nfl_url(2025, "pbp") == "http://localhost:9000/mirror/pbp/play_by_play_2025.parquet"


@pytest.mark.parametrize("base", ["file:///etc/", "ftp://example.com/", "/just/a/path", "mirror"])
def test_other_schemes_are_refused(monkeypatch: pytest.MonkeyPatch, base: str):
    monkeypatch.setenv("NFLVERSE_DOWNLOAD_BASE", base)

    with pytest.raises(ValueError, match="NFLVERSE_DOWNLOAD_BASE"):
        get_nfl_url(2025, "pbp")


def test_unknown_asset_kinds_are_refused(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("NFLVERSE_DOWNLOAD_BASE", raising=False)

    with pytest.raises(ValueError, match="Unknown nflverse asset kind"):
        get_nfl_url(2025, "rosters")
