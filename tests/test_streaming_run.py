"""Characterization test: pins streaming.run's output on a seeded league."""

import itertools
import json

import numpy as np
import polars as pl
import pytest

from fantasy import store
from fantasy.stages import streaming

SEASONS = (2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025)
CURRENT_WEEK = 5
LAST_WEEK = 8
GOLDEN_PROJECTION = [
    5.423431104055137, 4.735590051013607, 5.49093402582207, 5.1979011140460365,
    5.32970151785482, 4.66524550390311, 5.326537659812881, 5.012905494836143,
    6.347949432089203, 5.348257745082759, 5.742605495410378, 6.5849345924651095,
]  # fmt: skip
GOLDEN_DEF_RMSE = (3.219966796353995, 3.1785730628111017)
GOLDEN_K_RMSE = (4.159398356413483, 3.835230415252764)
TEAMS = ("AAA", "BBB")


def _inputs() -> dict[str, pl.DataFrame]:
    rng = np.random.default_rng(7)
    games, stats, kicks = [], [], []
    for season, week in itertools.product(SEASONS, range(1, LAST_WEEK + 1)):
        played = season < 2025 or week < CURRENT_WEEK
        for team, other in zip(TEAMS, reversed(TEAMS), strict=True):
            implied = float(rng.uniform(17, 28))
            roof = "dome" if (week + (team == "AAA")) % 3 == 0 else "outdoors"
            games.append(
                {
                    "game_id": f"{season}-{week}-{team}",
                    "game_type": "REG",
                    "team": team,
                    "opponent": other,
                    "roof": roof,
                    "season": season,
                    "week": week,
                    "points_against": int(rng.integers(6, 35)) if played else None,
                    "team_implied": implied,
                    "opp_implied": 45.0 - implied,
                    "is_home": team == "AAA",
                    "points_for": 20 if played else None,
                    "spread": 0.0,
                }
            )
            if played:
                stats.append(
                    {
                        "team": team,
                        "season_type": "REG",
                        "opponent_team": other,
                        "season": season,
                        "week": week,
                        "sacks_suffered": 2.0,
                        "passing_interceptions": 1.0,
                        "attempts": 30.0,
                        "passing_yards": float(rng.integers(150, 350)),
                        "rushing_yards": float(rng.integers(50, 150)),
                        "def_sacks": float(rng.integers(0, 6)),
                        "def_interceptions": float(rng.integers(0, 3)),
                        "def_tds": 0.0,
                        "special_teams_tds": 0.0,
                        "def_safeties": 0.0,
                        "def_fumbles_forced": float(rng.integers(0, 3)),
                        "fumble_recovery_opp": float(rng.integers(0, 2)),
                        "def_fg_blocks": 0.0,
                        "def_pat_blocks": 0.0,
                        "def_punt_blocks": 0.0,
                    }
                )
                if team == "AAA":
                    kicks.append(
                        {
                            "league_id": "L1",
                            "gsis_id": "K1",
                            "team": "AAA",
                            "opponent_team": "BBB",
                            "season_type": "REG",
                            "position": "K",
                            "season": season,
                            "week": week,
                            "points": float(rng.integers(0, 15)),
                            "team_implied": implied,
                            "roof": roof,
                        }
                    )
    scoring = {"sack": 1.0, "int": 2.0, "pts_allow_0": 10.0, "pts_allow_7_13": 4.0}
    league = {
        "league_key": "Test",
        "league_id": "L1",
        "current_week": CURRENT_WEEK,
        "scoring_settings": json.dumps(scoring),
    }
    sleeper = {"sleeper_id": "s1", "position": "K", "status": "Active", "team": "AAA"}
    return {
        "team_games": pl.from_dicts(games, schema_overrides=_dtypes("team_games")),
        "nfl_team_stats": pl.from_dicts(stats, schema_overrides=_dtypes("nfl_team_stats")),
        "player_points": pl.from_dicts(kicks, schema_overrides=_dtypes("player_points")),
        "nfl_team_efficiency": pl.DataFrame(schema=_dtypes("nfl_team_efficiency")),
        "nfl_team_pace": pl.DataFrame(schema=_dtypes("nfl_team_pace")),
        "nfl_player_stats": pl.DataFrame(schema=_dtypes("nfl_player_stats")),
        "leagues": pl.from_dicts([league]),
        "sleeper_players": pl.from_dicts([sleeper]),
        "id_map": pl.from_dicts([{"sleeper_id": "s1", "gsis_id": "K1", "nfl_team": "AAA"}]),
    }


def _dtypes(name: str) -> dict[str, pl.DataType]:
    return dict(store.SCHEMAS[name])


@pytest.fixture
def tables(monkeypatch: pytest.MonkeyPatch) -> dict[str, pl.DataFrame]:
    inputs = _inputs()
    written: dict[str, pl.DataFrame] = {}

    def read_table(name: str, area: str = "derived", data_dir=None) -> pl.DataFrame:  # type: ignore[no-untyped-def]
        if name not in inputs:
            raise FileNotFoundError(name)
        return inputs[name]

    def write_table(name, df, area="derived", data_dir=None):  # type: ignore[no-untyped-def]
        written[name] = df

    monkeypatch.setattr(store, "read_table", read_table)
    monkeypatch.setattr(store, "write_table", write_table)
    return written


def test_run_projects_def_and_k_for_the_remaining_weeks(tables: dict[str, pl.DataFrame]) -> None:
    report = streaming.run()

    out = tables["streaming_projection"]
    assert out.columns == ["league_id", "kind", "unit", "team", "week", "projection"]
    assert out["kind"].to_list() == ["DEF"] * 8 + ["K"] * 4
    assert out["unit"].to_list() == ["AAA", "BBB"] * 4 + ["K1"] * 4
    assert out["week"].to_list() == [5, 5, 6, 6, 7, 7, 8, 8, 5, 6, 7, 8]
    assert tables["defense_points"].height == 2 * (7 * LAST_WEEK + CURRENT_WEEK - 1)
    assert list(report) == ["Test DEF rmse (model, mean)", "Test K rmse (model, mean)"]
    assert out["projection"].to_list() == pytest.approx(GOLDEN_PROJECTION)
    assert report["Test DEF rmse (model, mean)"] == pytest.approx(GOLDEN_DEF_RMSE)
    assert report["Test K rmse (model, mean)"] == pytest.approx(GOLDEN_K_RMSE)


def test_run_archives_each_runs_projections_with_a_timestamp(
    tables: dict[str, pl.DataFrame],
) -> None:
    streaming.run()

    snapshot = tables["streaming_snapshots"]
    assert snapshot.columns == list(store.SCHEMAS["streaming_snapshots"])
    assert snapshot.height == tables["streaming_projection"].height
    assert snapshot["fetched_at"].n_unique() == 1
