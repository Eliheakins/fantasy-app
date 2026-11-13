import dataclasses
from collections.abc import Callable
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from store_fixture import engine_store, write_rows

from fantasy import _engine, _lineup, _outlook, _profile, data_api
from fantasy.sim.odds import LeagueData


@pytest.fixture
def store_ready(tmp_path: Path) -> Path:
    engine_store(tmp_path)
    return tmp_path


def test_profile_range_brackets_the_projection(store_ready: Path) -> None:
    out = data_api.player_profile("t", "G_QB", store_ready)
    assert (out["p10"], out["median"], out["p90"]) == pytest.approx((6.0, 10.0, 14.0))
    assert out["position"] == "QB"
    assert out["outlook_label"] == "Improving"
    assert out["why"].startswith("scoring 7.5 above")


def test_ros_over_replacement_is_ros_minus_best_other_free_agent(store_ready: Path) -> None:
    out = data_api.player_profile("t", "G_WR", store_ready)
    assert out["replacement_name"] is not None
    gap = out["ros_points"] - out["replacement_points"]
    assert out["ros_over_replacement"] == pytest.approx(gap)
    assert out["replacement_name"] != out["full_name"]


def test_a_free_agent_is_not_his_own_replacement(store_ready: Path) -> None:
    out = data_api.player_profile("t", "G_FA", store_ready)
    assert out["replacement_name"] != out["full_name"]


def test_injured_player_reports_status_and_a_zero_range(store_ready: Path) -> None:
    out = data_api.player_profile("t", "G_RB", store_ready)
    assert out["injury"] == "Out"
    assert out["chance_to_play"] == 0.0
    assert (out["p10"], out["p90"]) == (0.0, 0.0)


def test_unknown_player_is_an_empty_profile_not_an_error(store_ready: Path) -> None:
    out = data_api.player_profile("t", "G_NOBODY", store_ready)
    assert out["position"] is None and out["median"] is None and out["ros_points"] is None


def test_role_weeks_join_snap_share_and_target_share_by_week(tmp_path: Path) -> None:
    engine_store(tmp_path)
    write_rows(
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
        area="raw",
    )
    write_rows(
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
        area="raw",
    )
    out = data_api.player_profile("t", "G_WR", data_dir=tmp_path)["role_weeks"]
    assert out == [
        {"week": 1, "snap_share": 0.8, "target_share": None},
        {"week": 2, "snap_share": 0.6, "target_share": 0.3},
    ]


def test_role_weeks_are_empty_without_the_tables(store_ready: Path) -> None:
    assert data_api.player_profile("t", "G_WR", store_ready)["role_weeks"] == []


def _with_live(
    monkeypatch: pytest.MonkeyPatch, live: dict[str, tuple[float, float]]
) -> Callable[..., tuple[LeagueData, int]]:
    """Patch `_profile._league` to add `live`; returns the patched loader."""
    real = _engine._league

    def patched(key: str, *args: Any, **kwargs: Any) -> tuple[LeagueData, int]:
        data, mine = real(key, *args, **kwargs)
        return dataclasses.replace(data, live=live), mine

    monkeypatch.setattr(_profile, "_league", patched)
    return patched


def test_a_final_game_shows_the_result_and_the_next_weeks_range(
    store_ready: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = data_api.player_profile("t", "G_QB", store_ready)
    _with_live(monkeypatch, {"G_QB": (17.3, 0.0)})
    out = data_api.player_profile("t", "G_QB", store_ready)
    assert (out["result_week"], out["result_points"]) == (before["week"], 17.3)
    assert out["week"] is None or out["week"] > before["week"]


def test_a_game_under_way_matches_the_lineups_range(
    store_ready: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = {"G_QB": (4.0, 0.5)}
    patched = _with_live(monkeypatch, live)
    out = data_api.player_profile("t", "G_QB", store_ready)
    frame = _lineup.lineup("t", loaded=patched("t", store_ready), data_dir=store_ready)
    row = frame.filter(pl.col("gsis_id") == "G_QB").row(0, named=True)
    assert out["result_points"] is None
    assert (out["p10"], out["p90"], out["projection"]) == pytest.approx(
        (row["p10"], row["p90"], row["projection"])
    )


def test_out_players_are_not_the_replacement(store_ready: Path) -> None:
    out = data_api.player_profile("t", "G_QB", store_ready)
    assert out["replacement_name"] != "G_DL"  # Doubtful, not Out: stays eligible
    assert data_api.player_profile("t", "G_RB", store_ready)["is_out"] is True
    assert data_api.player_profile("t", "G_QB", store_ready)["is_out"] is False


def test_another_teams_player_and_the_viewed_team(store_ready: Path) -> None:
    mine = data_api.player_profile("t", "G_OPP", store_ready)
    assert mine["outlook_label"] == "Improving"  # scope "league" from my side
    theirs = data_api.player_profile("t", "G_OPP", store_ready, team=2)
    assert theirs["outlook_label"] == "Improving"
    assert theirs["why"] != "" and theirs["position"] is not None


def test_outlook_rows_are_cached_per_scope(
    store_ready: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    real = _outlook.player_outlook

    def counted(k: str, s: str, d: Path, t: int | None) -> Any:
        calls.append(s)
        return real(k, s, d, t)

    monkeypatch.setattr(_profile, "player_outlook", counted)
    _profile._outlook_rows.cache_clear()
    data_api.player_profile("t", "G_QB", store_ready)
    data_api.player_profile("t", "G_WR", store_ready)
    assert calls == ["mine"]
