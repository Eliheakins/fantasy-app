"""The bracket read and the playoff status labels (rows from `playoff_brackets`, odds from
`sim_bracket`)."""

from pathlib import Path

import polars as pl
import pytest
from store_fixture import engine_store, write_rows

from fantasy import data_api, store

SIX = {  # (r, m): (t1, t2, t1 from, t2 from, p)
    (1, 1): (3, 6, None, None, None),
    (1, 2): (4, 5, None, None, None),
    (2, 3): (2, None, None, ("w", 1), None),
    (2, 4): (1, None, None, ("w", 2), None),
    (2, 5): (None, None, ("l", 1), ("l", 2), 5),
    (3, 6): (None, None, ("w", 3), ("w", 4), 1),
    (3, 7): (None, None, ("l", 3), ("l", 4), 3),
}


def _row(r: int, m: int, **over: object) -> dict:
    t1, t2, f1, f2, p = SIX[(r, m)]
    base = {"league_id": "L1", "bracket": "winners", "r": r, "m": m, "t1": t1, "t2": t2, "p": p}
    for side, src in (("t1", f1), ("t2", f2)):
        if src:
            base |= {f"{side}_from_kind": src[0], f"{side}_from_m": src[1]}
    return base | over


def _store(tmp_path: Path, rows: list[dict], current: int, start: int = 2) -> None:
    engine_store(tmp_path)
    leagues = store.read_table("leagues", "raw", tmp_path).with_columns(
        current_week=pl.lit(current, pl.Int64), playoff_week_start=pl.lit(start, pl.Int64)
    )
    store.write_table("leagues", leagues, "raw", tmp_path)
    # sync stamps Sleeper's week; here it is the current week unless a row says otherwise
    synced = [{"fetched_week": current} | r for r in rows]
    write_rows(tmp_path, "playoff_brackets", synced, area="raw")
    odds = [
        {"league_id": "L1", "roster_id": t, "round": 1, "p_reach": 1.0, "p_win": 0.1 * t}
        for t in (3, 4, 5, 6)
    ]
    write_rows(tmp_path, "sim_bracket", odds)


ROUND_ONE = [_row(r, m) for r, m in SIX]
ROUND_TWO = [
    _row(1, 1, w=3, l=6),
    _row(1, 2, w=5, l=4),
    _row(2, 3, t2=3),
    _row(2, 4, t2=5),
    _row(2, 5, t1=6, t2=4),
    _row(3, 6),
    _row(3, 7),
]
ROUND_THREE = [
    _row(1, 1, w=3, l=6),
    _row(1, 2, w=5, l=4),
    _row(2, 3, t2=3, w=2, l=3),
    _row(2, 4, t2=5, w=1, l=5),
    _row(2, 5, t1=6, t2=4, w=4, l=6),
    _row(3, 6, t1=2, t2=1),
    _row(3, 7, t1=3, t2=5),
]
FINISHED = [*ROUND_THREE[:5], _row(3, 6, t1=2, t2=1, w=1, l=2), ROUND_THREE[6]]


def _status(path: Path, roster: int, week: int) -> str | None:
    return data_api.playoff_status("t", roster, week, path)


def test_the_bracket_is_no_data_before_it_is_set(tmp_path: Path) -> None:
    _store(tmp_path, ROUND_ONE, current=1)
    view = data_api.bracket("t", tmp_path)
    assert view.rounds == []
    assert view.message == "The bracket is set after week 1"


def test_a_missing_bracket_table_is_no_data(tmp_path: Path) -> None:
    engine_store(tmp_path)
    assert data_api.bracket("t", tmp_path).message


def test_a_seeded_bracket_lists_rounds_weeks_seeds_and_odds(tmp_path: Path) -> None:
    _store(tmp_path, ROUND_ONE, current=2)
    view = data_api.bracket("t", tmp_path, team=3)
    assert view.message is None
    assert [(r["round"], r["weeks"], len(r["matches"])) for r in view.rounds] == [
        (1, [2], 2), (2, [3], 3), (3, [4], 2)
    ]  # fmt: skip
    first = view.rounds[0]["matches"][0]
    assert first["t1"] == {
        "roster_id": 3, "team_name": "Team 3", "seed": 3, "from_kind": None, "from_m": None,
    }  # fmt: skip
    assert (first["t1_p_win"], first["t2_p_win"]) == pytest.approx((0.3, 0.6))
    assert first["is_mine"] is True
    assert first["winner"] is None and first["place"] is None
    assert view.rounds[0]["matches"][1]["is_mine"] is False
    waiting = view.rounds[1]["matches"][0]["t2"]
    assert (waiting["roster_id"], waiting["from_kind"], waiting["from_m"]) == (None, "w", 1)
    assert view.rounds[2]["matches"][0]["place"] == 1


def test_a_played_match_names_its_winner(tmp_path: Path) -> None:
    _store(tmp_path, ROUND_TWO, current=3)
    played = data_api.bracket("t", tmp_path).rounds[0]["matches"][0]
    assert (played["winner"], played["t1_p_win"]) == (3, None)


def test_status_is_a_round_against_a_named_opponent(tmp_path: Path) -> None:
    _store(tmp_path, ROUND_TWO, current=3)
    assert _status(tmp_path, 1, 3) == "Round 2 vs Team 5"
    assert _status(tmp_path, 3, 2) == "Round 1 vs Team 6"


def test_a_top_seed_has_a_bye_in_round_one(tmp_path: Path) -> None:
    _store(tmp_path, ROUND_ONE, current=2)
    assert _status(tmp_path, 1, 2) == "Bye this round"
    assert _status(tmp_path, 2, 2) == "Bye this round"


def test_an_unknown_opponent_is_to_be_decided(tmp_path: Path) -> None:
    _store(tmp_path, ROUND_ONE, current=2)
    assert _status(tmp_path, 1, 3) == "Round 2 vs TBD"


def test_a_team_out_of_the_title_path_is_eliminated(tmp_path: Path) -> None:
    _store(tmp_path, ROUND_THREE, current=4)
    assert _status(tmp_path, 6, 4) == "Eliminated"
    assert _status(tmp_path, 4, 4) == "Eliminated"


def test_consolation_games_are_labelled_by_place(tmp_path: Path) -> None:
    _store(tmp_path, ROUND_TWO, current=3)
    assert _status(tmp_path, 6, 3) == "Consolation: 5th place game vs Team 4"
    _store(tmp_path, ROUND_THREE, current=4)
    assert _status(tmp_path, 3, 4) == "Consolation: 3rd place game vs Team 5"


def test_the_final_winner_is_champion_and_the_loser_still_shows_the_final(tmp_path: Path) -> None:
    _store(tmp_path, FINISHED, current=4)
    assert _status(tmp_path, 1, 4) == "Champion"
    assert _status(tmp_path, 2, 4) == "Round 3 vs Mine"


def test_there_is_no_status_before_the_bracket_is_set_or_outside_the_playoffs(
    tmp_path: Path,
) -> None:
    _store(tmp_path, ROUND_ONE, current=1)
    assert _status(tmp_path, 3, 2) is None
    _store(tmp_path, ROUND_TWO, current=3)
    assert _status(tmp_path, 3, 1) is None
    assert _status(tmp_path, 9, 3) is None


def test_losers_rows_do_not_stretch_the_week_to_round_map(tmp_path: Path) -> None:
    final = {"t1_from_kind": "w", "t1_from_m": 1, "t2_from_kind": "w", "t2_from_m": 2}
    winners = [
        {"league_id": "L1", "bracket": "winners", "r": 1, "m": 1, "t1": 1, "t2": 4},
        {"league_id": "L1", "bracket": "winners", "r": 1, "m": 2, "t1": 2, "t2": 3},
        {"league_id": "L1", "bracket": "winners", "r": 2, "m": 3, "t1": 1, "t2": 2, "p": 1} | final,
    ]
    losers = [
        {"league_id": "L1", "bracket": "losers", "r": r, "m": r, "t1": 3, "t2": 4}
        for r in (1, 2, 3)
    ]
    _store(tmp_path, [*winners, *losers], current=16, start=14)
    leagues = store.read_table("leagues", "raw", tmp_path).with_columns(
        settings=pl.lit('{"playoff_round_type": 1}')
    )
    store.write_table("leagues", leagues, "raw", tmp_path)
    assert _status(tmp_path, 1, 16) == "Round 2 vs Theirs"


def test_a_losers_bracket_game_is_a_consolation_game_with_no_place(tmp_path: Path) -> None:
    losers = [
        {"league_id": "L1", "bracket": "losers", "r": 1, "m": 1, "t1": 7, "t2": 8, "p": 7},
        {"league_id": "L1", "bracket": "losers", "r": 1, "m": 2, "t1": 9, "t2": 10},
    ]
    _store(tmp_path, [*ROUND_ONE, *losers], current=2)
    assert _status(tmp_path, 8, 2) == "Consolation game vs 7"  # losers places count from 1
    assert _status(tmp_path, 9, 2) == "Consolation game vs 10"
    assert _status(tmp_path, 8, 3) is None  # no losers game in round 2


def test_the_league_row_label_reads_my_team_in_the_current_week(tmp_path: Path) -> None:
    _store(tmp_path, ROUND_ONE, current=2)
    [row] = data_api.leagues(tmp_path).to_dicts()
    assert data_api.league_label(row, tmp_path) == "Bye this round"  # roster 1 is mine
    assert data_api.league_label({**row, "roster_id": 3}, tmp_path) == "Round 1 vs Team 6"
    _store(tmp_path, FINISHED, current=5)
    assert data_api.league_label({**row, "current_week": 5}, tmp_path) == "Champion"
    assert data_api.league_label({**row, "current_week": 1}, tmp_path) is None
    assert data_api.league_label({**row, "roster_id": None}, tmp_path) is None


def test_a_league_with_an_unsupported_round_type_still_lists_with_no_playoff_weeks(
    tmp_path: Path,
) -> None:
    engine_store(tmp_path)
    leagues = store.read_table("leagues", "raw", tmp_path).with_columns(
        playoff_teams=pl.lit(6, pl.Int64), settings=pl.lit('{"playoff_round_type": 3}')
    )
    store.write_table("leagues", leagues, "raw", tmp_path)
    assert data_api.leagues(tmp_path)["playoff_weeks"].to_list() == [None]


def test_rows_synced_before_sleepers_week_reaches_the_start_are_not_read(tmp_path: Path) -> None:
    # week_rollover moved current_week to the start; Sleeper's leg (fetched_week) has not moved
    _store(tmp_path, [r | {"fetched_week": 1} for r in ROUND_ONE], current=2)
    assert _status(tmp_path, 3, 2) is None
    [row] = data_api.leagues(tmp_path).to_dicts()
    assert data_api.league_phase(row, tmp_path) is None
    view = data_api.bracket("t", tmp_path)
    assert view.rounds == [] and view.message == "The bracket is set after week 1"


def test_the_league_row_phase_reads_my_team_in_the_current_week(tmp_path: Path) -> None:
    _store(tmp_path, ROUND_ONE, current=2)
    [row] = data_api.leagues(tmp_path).to_dicts()
    assert data_api.league_phase(row, tmp_path) == "bye"  # roster 1 is mine
    assert data_api.league_phase({**row, "roster_id": 3}, tmp_path) == "playing"
    assert data_api.league_phase({**row, "current_week": 1}, tmp_path) == "regular"
    _store(tmp_path, FINISHED, current=5)
    assert data_api.league_phase({**row, "current_week": 5}, tmp_path) == "champion"
    assert data_api.league_phase({**row, "current_week": 5, "roster_id": 2}, tmp_path) == "over"
    assert data_api.league_phase({**row, "roster_id": None}, tmp_path) is None
