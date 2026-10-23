from pathlib import Path

import polars as pl
import pytest
from store_fixture import use_store, write_rows

from fantasy import data_api
from fantasy.stages.simulate import load_league_data

LEAGUE = {
    "league_id": "L1",
    "current_week": 3,
    "playoff_week_start": 15,
    "trade_deadline": None,
    "roster_positions": ["QB", "RB", "WR", "BN"],
}
# sleeper id -> (position, injury status, gsis id)
PLAYERS = {
    "qb": ("QB", None, "G_QB"),
    "rb": ("RB", "Out", "G_RB"),
    "wr": ("WR", "Questionable", "G_WR"),
    "te": ("TE", "IR", "G_TE"),
    "dl": ("WR", "Doubtful", "G_DL"),
    "nogsis": ("WR", None, None),
    "kick": ("K", None, "G_K"),
    "opp": ("WR", None, "G_OPP"),
    "fa": ("WR", None, "G_FA"),
    "freek": ("K", None, "G_FREEK"),
    "theirk": ("K", None, "G_THEIRK"),
}
MINE = ["qb", "rb", "wr", "te", "dl", "nogsis", "kick"]
WEEKS = [3, 4]


def build_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scores: list[tuple[float, float]],
    trade_deadline: int | None = None,
) -> None:
    """Two teams; `scores` is (team 1, team 2) points for weeks 1, 2, ... of completed play."""
    use_store(monkeypatch, tmp_path)
    league = {
        "league_key": "t",
        "season": 2026,
        "scoring_settings": "{}",
        "settings": "{}",
        "trade_deadline": trade_deadline,
        **{k: LEAGUE[k] for k in ("league_id", "current_week", "playoff_week_start")},
        "roster_positions": LEAGUE["roster_positions"],
    }
    write_rows(tmp_path, "leagues", [league])
    write_rows(
        tmp_path,
        "league_teams",
        [
            {"league_id": "L1", "roster_id": 1, "team_name": "Mine", "is_me": True},
            {"league_id": "L1", "roster_id": 2, "team_name": "Theirs", "is_me": False},
            *[
                {"league_id": "L1", "roster_id": r, "team_name": f"Team {r}", "is_me": False}
                for r in range(3, 7)
            ],
        ],
    )
    matchups = []
    for week, (a, b) in enumerate([*scores, *[(0.0, 0.0)] * len(WEEKS)], start=1):
        matchups += [
            {"league_id": "L1", "week": week, "roster_id": 1, "matchup_id": 1, "points": a},
            {"league_id": "L1", "week": week, "roster_id": 2, "matchup_id": 1, "points": b},
            *[
                {"league_id": "L1", "week": week, "roster_id": r, "matchup_id": m, "points": 50.0}
                for r, m in ((3, 2), (4, 2), (5, 3), (6, 3))
            ],
        ]
    write_rows(tmp_path, "matchups", matchups)
    owned = [(1, s) for s in MINE] + [(2, "opp"), (2, "theirk")]
    write_rows(
        tmp_path,
        "rosters",
        [{"league_id": "L1", "roster_id": r, "sleeper_id": s} for r, s in owned],
    )
    write_rows(
        tmp_path,
        "sleeper_players",
        [
            {
                "sleeper_id": s,
                "full_name": s,
                "position": pos,
                "team": "KC",
                "status": "Active",
                "injury_status": inj,
            }
            for s, (pos, inj, _) in PLAYERS.items()
        ],
    )
    write_rows(
        tmp_path,
        "id_map",
        [{"sleeper_id": s, "gsis_id": g, "nfl_team": "KC"} for s, (_, _, g) in PLAYERS.items()],
    )
    base = {"league_id": "L1", "season": 2026, "projection": 10.0, "has_history": True}
    skill = [(g, pos) for _, (pos, _, g) in PLAYERS.items() if g and pos != "K"]
    future = [
        {**base, "gsis_id": g, "position": pos, "team": "KC", "week": w, "is_future": True}
        for g, pos in skill
        for w in WEEKS
    ]
    past = [{**future[0], "week": 1, "is_future": False}]
    write_rows(tmp_path, "proj_baseline", future + past)
    spread = [
        {"league_id": "L1", "position": pos, "tier": -1, "cv": 0.5}
        for pos in ("QB", "RB", "WR", "TE")
    ]
    write_rows(tmp_path, "marginals", spread)
    for name in ("correlation_pairs", "player_points", "matchup_players"):
        write_rows(tmp_path, name)
    for name in ("nfl_injuries", "nfl_schedules"):
        write_rows(tmp_path, name)


def week_projection(projections: pl.DataFrame, gsis_id: str, week: int) -> float:
    rows = projections.filter((pl.col("gsis_id") == gsis_id) & (pl.col("week") == week))
    return float(rows["projection"].item())


def test_roster_keeps_only_mapped_skill_players(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)])
    data = load_league_data(LEAGUE)
    mine = data.rosters.filter(pl.col("roster_id") == 1)["gsis_id"].to_list()
    assert sorted(mine) == ["G_DL", "G_QB", "G_RB", "G_TE", "G_WR"]  # no K, no unmapped id
    assert data.rosters.filter(pl.col("roster_id") == 2)["gsis_id"].to_list() == ["G_OPP"]


def test_wins0_counts_a_tie_as_half_a_win(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_store(tmp_path, monkeypatch, [(100.0, 100.0), (110.0, 90.0)])
    data = load_league_data(LEAGUE)
    assert (data.wins0[1], data.wins0[2]) == (1.5, 0.5)
    assert (data.points0[1], data.points0[2]) == (210.0, 190.0)


def test_injury_fallback_zeroes_out_and_ir_and_discounts_questionable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)])
    assert "injury model" in data_api.missing_layers(tmp_path)
    projections = load_league_data(LEAGUE).projections
    assert week_projection(projections, "G_QB", 3) == pytest.approx(10.0)
    assert week_projection(projections, "G_RB", 3) == 0.0
    assert week_projection(projections, "G_TE", 4) == 0.0  # IR sits four games from now
    assert week_projection(projections, "G_WR", 3) == pytest.approx(7.6)
    assert week_projection(projections, "G_WR", 4) == pytest.approx(10.0)
    assert week_projection(projections, "G_DL", 3) == pytest.approx(0.2)


def test_missing_effect_tables_do_not_stop_the_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)])
    missing = data_api.missing_layers(tmp_path)
    assert {"injury model", "outlook", "matchup and offense effects"} <= set(missing)
    data = load_league_data(LEAGUE)
    assert data.trade_deadline == 99 and data.roster_ids == [1, 2, 3, 4, 5, 6]
    assert data.injuries["G_RB"][0] == "Out"
