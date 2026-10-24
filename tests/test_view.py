from pathlib import Path

import polars as pl
import pytest
from store_fixture import write_rows

from fantasy import _view as view
from fantasy._schemas import ENGINE_SCHEMAS


def lineup_rows() -> pl.DataFrame:
    """A, B start; C, D are on the bench. Sleeper has A and C set."""
    rows = [
        ("QB", "A", "Ann", True, True),
        ("RB", "B", "Bob", False, True),
        ("BN", "C", "Cy", True, False),
        ("BN", "D", "Di", False, False),
    ]
    return pl.DataFrame(
        [
            {
                "slot": slot,
                "gsis_id": gid,
                "full_name": name,
                "position": "RB",
                "projection": 10.0,
                "p10": 5.0,
                "p90": 15.0,
                "starting_now": now,
                "recommended": rec,
                "injury": None,
                "injury_note": None,
                "locked": False,
                "actual": 0.0,
                "game": "Not started",
            }
            for slot, gid, name, now, rec in rows
        ],
        schema=ENGINE_SCHEMAS["lineup"],
    )


def odds_rows(tag: str = "start a gamble") -> pl.DataFrame:
    def row(option: str, ids: list[str], slots: list[str], win: float, t: str = "") -> dict:
        return {
            "option": option,
            "win_prob": win,
            "expected_points": 20.0,
            "gsis_ids": ids,
            "slots": slots,
            "share_better": 0.6,
            "tag": t,
            "floor": 1.0,
            "median": 2.0,
            "ceiling": 3.0,
            "script": "Toss-up (50% to win)",
        }

    return pl.DataFrame(
        [
            row("max_points", ["A", "B"], ["QB", "RB"], 0.50),
            row("win_prob", ["A", "D"], ["QB", "RB"], 0.55, tag),
            row("ceiling", ["B", "D"], ["QB", "RB"], 0.52),
            row("floor", ["A", "B"], ["QB", "RB"], 0.50),
            row("sleeper_now", ["A", "C"], ["QB", "RB"], 0.40),
        ],
        schema=ENGINE_SCHEMAS["win_probability"],
    )


@pytest.mark.parametrize(
    ("wins", "losses", "ties", "text"),
    [
        (3, 1, 0, "3-1"),
        (3, 1, None, "3-1"),
        (3, 1, 2, "3-1-2"),
        (None, None, None, "no record yet"),
        (2, None, 0, "no record yet"),
    ],
)
def test_record_string(wins: int | None, losses: int | None, ties: int | None, text: str) -> None:
    assert view.record_string(wins, losses, ties) == text


def test_objective_option_maps_the_four_objectives() -> None:
    assert view.OBJECTIVES == {
        "expected_points": "max_points",
        "win_probability": "win_prob",
        "max_ceiling": "ceiling",
        "max_floor": "floor",
    }


def test_reslot_expected_points_keeps_the_rows_as_they_are() -> None:
    rows = lineup_rows()
    assert view.reslot(rows, odds_rows(), "expected_points").equals(rows)


def test_reslot_win_probability_moves_players_into_the_options_slots() -> None:
    out = view.reslot(lineup_rows(), odds_rows(), "win_probability")
    by_id = {r["gsis_id"]: r for r in out.iter_rows(named=True)}
    assert (by_id["A"]["slot"], by_id["A"]["recommended"]) == ("QB", True)
    assert (by_id["D"]["slot"], by_id["D"]["recommended"]) == ("RB", True)
    assert (by_id["B"]["slot"], by_id["B"]["recommended"]) == ("BN", False)
    assert (by_id["C"]["slot"], by_id["C"]["recommended"]) == ("BN", False)


def test_reslot_without_odds_or_with_unknown_objective() -> None:
    rows = lineup_rows()
    assert view.reslot(rows, pl.DataFrame(), "max_floor").equals(rows)
    with pytest.raises(ValueError, match="objective"):
        view.reslot(rows, odds_rows(), "nope")


def test_reslot_does_not_change_its_input() -> None:
    rows = lineup_rows()
    before = rows.clone()
    view.reslot(rows, odds_rows(), "max_ceiling")
    assert rows.equals(before)


def test_lineup_changes_marks_start_and_sit_against_sleeper() -> None:
    out = view.lineup_changes(lineup_rows())
    assert dict(zip(out["gsis_id"], out["change"], strict=True)) == {
        "A": "",
        "B": "Start",
        "C": "Sit",
        "D": "",
    }


def test_lineup_changes_are_blank_when_sleeper_lineup_is_unknown() -> None:
    rows = lineup_rows().with_columns(starting_now=pl.lit(False))
    assert set(view.lineup_changes(rows)["change"]) == {""}


def test_swap_note_names_who_comes_in_and_out() -> None:
    note = view.swap_note(lineup_rows(), odds_rows())
    assert note is not None and note.differs
    assert (note.players_in, note.players_out) == (["Di"], ["Bob"])
    assert note.text == (
        "Start a gamble: start Di over Bob (55.0% vs 50.0%). In games where the two "
        "lineups disagree, this one wins 60% of the time."
    )


def test_swap_note_when_the_pick_is_the_max_points_lineup() -> None:
    note = view.swap_note(lineup_rows(), odds_rows("same as max points"))
    assert note is not None and not note.differs
    assert note.text is None and note.players_in == [] and note.players_out == []


def test_swap_note_is_none_without_odds() -> None:
    assert view.swap_note(lineup_rows(), pl.DataFrame()) is None


def test_comparison_relabels_options_drops_sleeper_and_has_expected_points() -> None:
    out = view.comparison(odds_rows())
    assert out["option"].to_list() == [
        "Expected points",
        "Win probability",
        "Max ceiling",
        "Max floor",
    ]
    assert out.columns == ["option", "win_prob", "expected_points", "floor", "median", "ceiling"]


def test_lineup_summary_reports_totals_gap_and_chance() -> None:
    summary = view.lineup_summary(lineup_rows(), odds_rows(), "win_probability")
    assert summary.shown_points == 20.0  # A + D start
    assert summary.sleeper_points == 20.0  # A + C set in Sleeper
    assert summary.gap == pytest.approx(0.0)
    assert summary.win_prob == 0.55


def test_lineup_summary_without_a_known_sleeper_lineup() -> None:
    rows = lineup_rows().with_columns(starting_now=pl.lit(False))
    summary = view.lineup_summary(rows, pl.DataFrame(), "expected_points")
    assert summary.sleeper_points is None and summary.gap is None and summary.win_prob is None


def test_asset_labels() -> None:
    assets = pl.DataFrame(
        {"gsis_id": ["A"], "full_name": ["Ann"], "position": ["RB"], "ros_points": [101.6]}
    )
    assert view.asset_labels(assets) == {"A": "Ann (RB, 102 pts)"}


def test_roster_moves_warning_only_when_there_are_moves() -> None:
    schema = {
        "team_name": pl.String,
        "action": pl.String,
        "full_name": pl.String,
        "position": pl.String,
    }
    assert view.roster_moves_warning(pl.DataFrame(schema=schema)) is None
    one = pl.DataFrame(
        {"team_name": ["M"], "action": ["dropped"], "full_name": ["x"], "position": ["WR"]}
    )
    assert view.roster_moves_warning(one) == "Automatic roster moves to keep sizes equal:"


def test_unmatched_names_lists_name_position_and_team() -> None:
    frame = pl.DataFrame(
        {"sleeper_id": ["1"], "full_name": ["Zed"], "position": ["WR"], "team": ["KC"]}
    )
    assert view.unmatched_names(frame) == ["Zed (WR, KC)"]


def test_my_odds_history_needs_two_runs_and_filters_to_my_team() -> None:
    def history(runs: list[str]) -> pl.DataFrame:
        return pl.DataFrame(
            [
                {"run_at": r, "team_name": t, "roster_id": rid, "p_playoffs": 0.5, "p_title": 0.1}
                for r in runs
                for t, rid in (("Mine", 1), ("Theirs", 2))
            ]
        )

    odds = pl.DataFrame({"roster_id": [1, 2], "is_me": [True, False]})
    two = view.my_odds_history(history(["2", "1"]), odds)
    assert two["run_at"].to_list() == ["1", "2"] and set(two["roster_id"]) == {1}
    assert view.my_odds_history(history(["1"]), odds).is_empty()


def test_trade_deadline_reads_the_leagues_table(
    tmp_path: Path,
) -> None:
    write_rows(tmp_path, "leagues", [{"league_key": "t", "trade_deadline": 11}])
    assert view.trade_deadline("t", tmp_path) == 11
    assert view.trade_deadline("other", tmp_path) is None
    write_rows(tmp_path, "leagues", [{"league_key": "t", "trade_deadline": None}])
    assert view.trade_deadline("t", tmp_path) is None


def test_action_fields_parse_points_and_take_share_better_from_the_win_prob_row() -> None:
    actions = pl.DataFrame(
        {
            "kind": ["Lineup", "Win probability", "Injury", "Waiver"],
            "text": [
                "Start A over B (+2.5 points)",
                "Boost: start C over D (55.0% vs 50.0% to win)",
                "E is Out and in your lineup",
                "Add F, drop G: +1.0% playoff odds, -0.4 points",
            ],
        }
    )
    odds = pl.DataFrame(
        {"option": ["max_points", "win_prob"], "share_better": [0.5, 0.8]},
    )

    out = view.action_fields(actions, odds)

    assert [r["delta_points"] for r in out] == [2.5, None, None, -0.4]
    assert [r["share_better"] for r in out] == [None, 0.8, None, None]
    assert [r["text"] for r in out] == actions["text"].to_list()


def test_action_fields_without_odds_leave_share_better_null() -> None:
    actions = pl.DataFrame({"kind": ["Win probability"], "text": ["x"]})
    assert view.action_fields(actions, None)[0]["share_better"] is None
