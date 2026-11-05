from pathlib import Path

import polars as pl
import pytest
from test_data_api_characterization import _engine_store

from fantasy import data_api, store


@pytest.fixture
def store_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _engine_store(tmp_path, monkeypatch)


def test_profile_range_brackets_the_projection(store_ready: None) -> None:
    out = data_api.player_profile("t", "G_QB")
    assert (out["p10"], out["median"], out["p90"]) == pytest.approx((6.0, 10.0, 14.0))
    assert out["position"] == "QB"
    assert out["outlook_label"] == "Improving"
    assert out["why"].startswith("scoring 7.5 above")


def test_ros_over_replacement_is_ros_minus_best_other_free_agent(store_ready: None) -> None:
    out = data_api.player_profile("t", "G_WR")
    assert out["replacement_name"] is not None
    gap = out["ros_points"] - out["replacement_points"]
    assert out["ros_over_replacement"] == pytest.approx(gap)
    assert out["replacement_name"] != out["full_name"]


def test_a_free_agent_is_not_his_own_replacement(store_ready: None) -> None:
    out = data_api.player_profile("t", "G_FA")
    assert out["replacement_name"] != out["full_name"]


def test_injured_player_reports_status_and_a_zero_range(store_ready: None) -> None:
    out = data_api.player_profile("t", "G_RB")
    assert out["injury"] == "Out"
    assert out["chance_to_play"] == 0.0
    assert (out["p10"], out["p90"]) == (0.0, 0.0)


def test_unknown_player_is_an_empty_profile_not_an_error(store_ready: None) -> None:
    out = data_api.player_profile("t", "G_NOBODY")
    assert out["position"] is None and out["median"] is None and out["ros_points"] is None


def _raw(tmp_path: Path, name: str, rows: list[dict]) -> None:
    schema = store.SCHEMAS[name]
    frame = pl.DataFrame([{**dict.fromkeys(schema), **r} for r in rows], schema=schema)
    store.write_table(name, frame, "raw", tmp_path)


def test_role_weeks_join_snap_share_and_target_share_by_week(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    _raw(
        tmp_path,
        "nfl_snaps",
        [
            {
                "gsis_id": "G_WR",
                "season": 2026,
                "week": 1,
                "offense_snaps": 40.0,
                "offense_pct": 0.8,
            },
            {
                "gsis_id": "G_WR",
                "season": 2026,
                "week": 2,
                "offense_snaps": 30.0,
                "offense_pct": 0.6,
            },
            {
                "gsis_id": "G_QB",
                "season": 2026,
                "week": 1,
                "offense_snaps": 60.0,
                "offense_pct": 1.0,
            },
        ],
    )
    _raw(
        tmp_path,
        "nfl_player_stats",
        [
            {
                "player_id": "G_WR",
                "season": 2026,
                "week": 2,
                "season_type": "REG",
                "target_share": 0.3,
            },
        ],
    )
    out = data_api.player_profile("t", "G_WR")["role_weeks"]
    assert out == [
        {"week": 1, "snap_share": 0.8, "target_share": None},
        {"week": 2, "snap_share": 0.6, "target_share": 0.3},
    ]


def test_role_weeks_are_empty_without_the_tables(store_ready: None) -> None:
    assert data_api.player_profile("t", "G_WR")["role_weeks"] == []
