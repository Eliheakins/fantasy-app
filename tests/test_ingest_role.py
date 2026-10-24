import datetime as dt

import polars as pl
import pytest

from fantasy.stages import ingest_role as r


def test_old_depth_charts_keep_the_best_offensive_depth_slot_per_player_week() -> None:
    old = pl.DataFrame(
        {
            "season": [2023, 2023, 2023, 2023],
            "week": [1, 1, 1, 1],
            "game_type": ["REG", "REG", "REG", "PRE"],
            "formation": ["Offense", "Offense", "Defense", "Offense"],
            "position": ["WR", "WR", "CB", "WR"],
            "gsis_id": ["A", "A", "A", "A"],
            "depth_team": ["2", "1", "1", "3"],
        }
    )
    out = r.old_depth(old)
    assert out.to_dicts() == [{"gsis_id": "A", "season": 2023, "week": 1, "depth_rank": 1.0}]


def test_new_depth_snapshots_use_the_latest_one_before_the_game_day() -> None:
    snaps = pl.DataFrame(
        {
            "team": ["KC", "KC", "KC"],
            "dt": ["2025-08-01T10:00:00Z", "2025-09-05T10:00:00Z", "2025-09-20T10:00:00Z"],
            "gsis_id": ["A", "A", "A"],
            "pos_abb": ["WR", "WR", "WR"],
            "pos_rank": [3, 2, 1],
        }
    )
    games = pl.DataFrame(
        {
            "season": [2025, 2025, 2025],
            "week": [1, 2, 3],
            "team": ["KC", "KC", "KC"],
            "gameday": ["2025-09-07", "2025-09-14", "2025-09-21"],
        }
    )
    out = r.new_depth(snaps, games).sort("week")
    assert out["depth_rank"].to_list() == [2.0, 2.0, 1.0]  # week 3 sees the Sep 20 snapshot


def test_age_and_draft_pick_come_from_the_roster() -> None:
    roster = pl.DataFrame(
        {
            "gsis_id": ["A", "B"],
            "season": [2025, 2025],
            "week": [1, 1],
            "game_type": ["REG", "REG"],
            "birth_date": [dt.date(2000, 9, 1), dt.date(1995, 3, 1)],
            "years_exp": [3, 8],
            "draft_number": [10, None],
        }
    )
    out = r.roster_features(roster).sort("gsis_id")
    assert out["age"].to_list() == pytest.approx([25.0, 30.5], abs=0.05)
    assert out["draft_pick"].to_list() == [10.0, 300.0]  # undrafted players get a late pick


def test_a_ranking_counts_for_the_next_game_week_and_the_last_scrape_before_it_wins() -> None:
    cal = pl.DataFrame(
        {
            "season": [2025, 2025],
            "week": [1, 2],
            "first_game": [dt.date(2025, 9, 4), dt.date(2025, 9, 11)],
        }
    )
    rankings = pl.DataFrame(
        {
            "id": ["1", "1", "1", "1"],
            "scrape_date": ["2025-08-10", "2025-09-02", "2025-09-03", "2025-09-09"],
            "ecr": [30.0, 12.0, 10.0, 8.0],
            "sd": [3.0, 2.0, 1.5, 1.0],
            "best": [20.0, 8.0, 7.0, 6.0],
            "worst": [40.0, 16.0, 14.0, 10.0],
        }
    )
    out = r.matched_rankings(rankings, cal).sort("week")
    # the August scrape is more than nine days before week 1; week 1 takes the Sep 3 scrape
    assert out["week"].to_list() == [1, 2]
    assert out["ecr"].to_list() == [10.0, 8.0]
    assert out["range"].to_list() == [7.0, 4.0]
