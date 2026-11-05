import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from fantasy import store
from fantasy.stages import news_archive as na

# synthetic players-file entries in Sleeper's shape (not real players)
RAW = {
    "1": {
        "position": "RB",
        "team": "KC",
        "status": "Active",
        "injury_status": "Questionable",
        "injury_body_part": "Ankle",
        "injury_notes": "Sprain",
        "injury_start_date": None,
        "practice_participation": "Limited",
        "depth_chart_position": "RB",
        "depth_chart_order": 1,
        "news_updated": 1792854657306,
        "team_changed_at": None,
    },
    "2": {"position": "WR", "team": None, "status": "Inactive", "depth_chart_order": "2"},
    "3": {"position": "K", "team": "KC", "status": "Active"},
    "4": {"position": "DEF", "team": "KC"},
}


def write_cache(data_dir: Path, raw: dict, day: str) -> None:
    cache = data_dir / "raw" / "sleeper_players_cache.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(raw))
    stamp = datetime.fromisoformat(f"{day}T15:00:00+00:00").timestamp()
    os.utime(cache, (stamp, stamp))


def test_status_frame_keeps_skill_players_and_the_fields_sync_sleeper_drops() -> None:
    df = na.status_frame(RAW, "2026-10-26T15:00:00+00:00")
    assert list(df.columns) == list(store.SCHEMAS["sleeper_player_status"])
    assert sorted(df["sleeper_id"]) == ["1", "2"]  # K and DEF are left out
    first = df.filter(df["sleeper_id"] == "1").row(0, named=True)
    assert first["injury_notes"] == "Sprain" and first["practice_participation"] == "Limited"
    assert first["depth_chart_order"] == 1 and first["news_updated"] == 1792854657306
    second = df.filter(df["sleeper_id"] == "2").row(0, named=True)
    assert second["depth_chart_order"] == 2 and second["injury_status"] is None


def test_run_appends_at_most_one_snapshot_per_day_stamped_with_the_files_fetch_time(
    tmp_path: Path,
) -> None:
    write_cache(tmp_path, RAW, "2026-10-25")
    assert na.run(tmp_path) == 2
    assert na.run(tmp_path) == 0  # same day: skipped
    write_cache(tmp_path, RAW, "2026-10-26")
    assert na.run(tmp_path) == 2
    archive = store.read_table("sleeper_player_status", "archive", tmp_path)
    assert archive.height == 4  # appended, not replaced
    assert sorted(archive["fetched_at"].unique()) == [
        "2026-10-25T15:00:00+00:00",
        "2026-10-26T15:00:00+00:00",
    ]


def test_a_missing_or_broken_players_file_fails_soft_and_keeps_the_archive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert na.run(tmp_path) == 0  # no players file yet
    assert "warning" in capsys.readouterr().out
    write_cache(tmp_path, RAW, "2026-10-25")
    assert na.run(tmp_path) == 2
    cache = tmp_path / "raw" / "sleeper_players_cache.json"
    cache.write_text("{not json")
    assert na.run(tmp_path) == 0
    assert "warning" in capsys.readouterr().out
    assert store.read_table("sleeper_player_status", "archive", tmp_path).height == 2
