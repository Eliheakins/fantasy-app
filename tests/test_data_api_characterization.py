"""Pins data_api outputs on the fixture league before and after structural refactors."""

from datetime import UTC, datetime
from pathlib import Path

import polars as pl
import pytest
from store_fixture import write_rows
from test_simulate_load import build_store

from fantasy import data_api, store

NOW = datetime(2026, 9, 1, tzinfo=UTC)
LEVELS = range(1, 100)
SKILL = (("G_QB", "QB"), ("G_WR", "WR"), ("G_RB", "RB"), ("G_OPP", "WR"))


def _engine_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    build_store(tmp_path, monkeypatch, [(100.0, 90.0)])
    write_rows(tmp_path, "trending")
    marginals = [
        {
            "league_id": "L1",
            "position": pos,
            "tier": tier,
            "tau": round(k / 100, 2),
            "ratio": 0.4 + k / 100 + 0.1 * tier,
            "cv": 0.5,
            "proj_max": {0: 8.0, 1: 14.0}.get(tier),
        }
        for pos in ("QB", "RB", "WR", "TE")
        for tier in (-1, 0, 1, 2)
        for k in LEVELS
    ]
    write_rows(tmp_path, "marginals", marginals)
    points = [
        {"league_id": "L1", "gsis_id": g, "season": 2026, "week": w, "points": 5.0 + w + len(g) % 3}
        | {"season_type": "REG", "position": pos}
        for g, pos in SKILL
        for w in (1, 2)
    ]
    write_rows(tmp_path, "player_points", points)
    schema = store.SCHEMAS["nfl_ff_opportunity"]
    opportunity = [
        {"player_id": g, "season": 2026, "week": w, "position": pos, "posteam": "KC"}
        | {"total_fantasy_points_exp": 7.0, "rec_attempt": 5.0, "receptions_exp": 4.0}
        for g, pos in SKILL
        for w in (1, 2)
    ]
    frame = pl.DataFrame([{**dict.fromkeys(schema), **r} for r in opportunity], schema=schema)
    store.write_table("nfl_ff_opportunity", frame, "raw", tmp_path)


def _round(row: dict) -> dict:
    return {k: round(v, 6) if isinstance(v, float) else v for k, v in row.items()}


def test_win_probability_options_are_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    out = data_api.win_probability("t", n_sims=2000, now=NOW)
    rows = [_round(r) for r in out.iter_rows(named=True)]
    same = {
        "win_prob": 0.867,
        "expected_points": 17.6,
        "gsis_ids": ["G_QB", "G_RB", "G_WR"],
        "slots": ["QB", "RB", "WR"],
        "share_better": 0.5,
        "floor": 9.040432,
        "median": 18.255272,
        "ceiling": 24.589722,
        "script": "Favorite (87% to win): protect the floor",
    }
    tags = {"max_points": "", "win_prob": "same as max points", "ceiling": "", "floor": ""}
    assert rows == [{"option": o, "tag": t, **same} for o, t in tags.items()]
    assert data_api.win_probability("t", 4, n_sims=2000, now=NOW).is_empty()


OUTLOOK_PINS = {
    "mine": {
        "G_QB": ("Improving", "scoring 7.5 above what usage is worth"),
        "G_RB": (
            "Injured",
            "scoring 7.5 above what usage is worth; Out: 0% to play, 100% next game",
        ),
        "G_WR": (
            "Improving",
            "scoring 7.5 above what usage is worth; Questionable: 76% to play, 100% next game",
        ),
        "G_DL": ("Injured", "Doubtful: 2% to play, 100% next game"),
        "G_TE": ("Injured", "IR, out at least 4 games"),
    },
    "league": {"G_OPP": ("Improving", "scoring 8.5 above what usage is worth")},
    "free": {"G_FA": ("No recent games", "")},
}


@pytest.mark.parametrize("scope", OUTLOOK_PINS)
def test_player_outlook_labels_and_reasons_are_pinned(
    scope: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    out = data_api.player_outlook("t", scope)
    got = {r["gsis_id"]: (r["label"], r["why"]) for r in out.iter_rows(named=True)}
    assert got == OUTLOOK_PINS[scope]
    owners = set(out["owner"])
    assert owners == {"mine": {"You"}, "league": {"Theirs"}, "free": {"Free agent"}}[scope]


def test_lineup_projection_and_spread_are_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    out = data_api.lineup("t", now=NOW)
    qb = _round(out.filter(pl.col("gsis_id") == "G_QB").row(0, named=True))
    assert (qb["slot"], qb["projection"], qb["p10"], qb["p90"]) == ("QB", 10.0, 6.0, 14.0)
    assert qb["game"] == "Not started"


def test_functions_that_read_leagues_see_a_patched_leagues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _engine_store(tmp_path, monkeypatch)
    write_rows(
        tmp_path,
        "sim_season",
        [
            {"league_id": "L1", "roster_id": 1, "team_name": "Mine", "p_title": 0.5},
            {"league_id": "L1", "roster_id": 2, "team_name": "Theirs", "p_title": 0.1},
        ],
    )
    write_rows(tmp_path, "sim_seeds", [{"league_id": "L1", "roster_id": 1, "seed": 1, "p": 1.0}])
    write_rows(
        tmp_path,
        "streaming_projection",
        [
            {
                "league_id": "L1",
                "kind": "K",
                "unit": "G_K",
                "team": "KC",
                "week": 3,
                "projection": 6.0,
            }
        ],
    )
    seen = pl.DataFrame(
        {
            "league_key": ["zz"],
            "league_id": ["L1"],
            "roster_id": [1],
            "current_week": [3],
            "num_teams": [6],
        }
    )
    monkeypatch.setattr(data_api, "leagues", lambda *args, **kwargs: seen)
    assert data_api.roster("zz", tmp_path).height == 7
    assert data_api.season_odds("zz", tmp_path)["is_me"].to_list() == [True, False]
    assert data_api.seed_distribution("zz")["seed"].to_list() == [1]
    assert data_api.streamers("zz", "K")["unit"].to_list() == ["G_K"]
    odds_history = data_api.odds_history("zz", tmp_path)
    assert odds_history.columns[:2] == ["run_at", "team_name"]


def test_outlook_label_and_reasons_follow_their_thresholds() -> None:
    from fantasy._outlook import _label, _why

    row = {
        "factor": 0.9,
        "vacancy": 0.6,
        "matchup": 0.0,
        "offense": -0.5,
        "recent_ppg": 12.0,
        "expected_ppg": 9.0,
        "games": 3,
        "chance_to_play": 1.0,
    }
    assert _why(row, "Questionable") == (
        "first games back (90% of projection); teammates out (+0.6 points); "
        "offense efficiency regression (loss of 0.5 points); "
        "scoring 3.0 above what usage is worth; Questionable"
    )
    assert [_label(row, c) for c in (1.5, -1.5, 1.4, None)] == [
        "Improving",
        "Regressing",
        "Steady",
        "No recent games",
    ]
    assert _label({**row, "chance_to_play": 0.35}, 5.0) == "Injured"


def test_a_player_who_is_out_has_a_zero_range_and_questionable_players_keep_theirs() -> None:
    from types import SimpleNamespace

    from fantasy import _lineup
    from fantasy.sim.lineup import Player

    flags = {"a": ("Out", None, None), "b": ("Questionable", None, None), "c": ("IR", None, None)}
    data = SimpleNamespace(injuries=flags)
    assert [_lineup._is_out(data, g) for g in "abcd"] == [True, False, True, False]  # type: ignore[arg-type]
    player = Player("a", "WR", 5.0)
    assert _lineup._spread(player, 0.9, {}, {}, {}, out=True) == 0.0
