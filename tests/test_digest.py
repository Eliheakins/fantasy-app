"""Weekly digest reads (last week, projection misses, odds change, stored move ideas) and the
stage that writes the ideas."""

from pathlib import Path
from typing import Any

import polars as pl
import pytest
from store_fixture import write_rows
from test_league_view import LID, league  # noqa: F401  (league is a fixture)

from fantasy import _digest, data_api, store
from fantasy._engine import viewing_team
from fantasy.stages import digest as stage

AT = "2026-10-25T08:00:00+00:00"


def me_row(path: Path, week: int) -> dict[str, Any]:
    """My row in `leagues` as of `week`, as `_my_league` builds it."""
    row = data_api.leagues(path).row(0, named=True)
    return {**row, "current_week": week}


def test_last_week_gives_result_opponent_and_the_week_s_luck_and_bench(league: Path) -> None:
    # team 3 in week 1 (current week 2): beat team 4, 80 to 70, against 1 of 3 all-play wins
    me = {**me_row(league, 2), "roster_id": 3, "team_name": "T3"}
    out = _digest.last_week(me, league)
    row = out.row(0, named=True)
    assert (row["week"], row["team_name"], row["opponent"]) == (1, "T3", "T4")
    assert (row["points"], row["opp_points"], row["result"]) == (80.0, 70.0, "W")
    assert row["luck"] == pytest.approx(1 - 1 / 3)
    assert row["bench_points_left"] is None  # no player rows for team 3: unknown, not zero


def test_last_week_bench_points_are_that_week_only(league: Path) -> None:
    out = _digest.last_week(me_row(league, 2), league)
    row = out.row(0, named=True)
    assert (row["result"], row["opponent"]) == ("W", "T2")
    assert row["bench_points_left"] == 5.0  # 20 + 15 + 5 hindsight best against 20 + 10 + 5


def test_last_week_is_empty_in_week_one_and_has_no_luck_in_the_playoffs(league: Path) -> None:
    assert _digest.last_week(me_row(league, 1), league).is_empty()
    write_rows(
        league,
        "leagues",
        [
            {
                "league_key": "t", "league_id": LID, "current_week": 3, "playoff_week_start": 2,
                "roster_positions": ["QB", "RB", "K", "BN", "BN"], "scoring_settings": "{}",
            }
        ],
    )  # fmt: skip
    playoffs = _digest.last_week(me_row(league, 3), league)
    # week 2 has no luck or bench figure once the playoffs have begun
    assert playoffs.row(0, named=True)["luck"] is None


def test_data_api_last_week_follows_the_viewed_team(league: Path) -> None:
    with viewing_team(3):
        row = data_api.last_week("t", league).row(0, named=True)
    assert row["team_name"] == "T3" and row["opponent"] == "T1"
    assert data_api.last_week("nope", league).columns == data_api.last_week("t", league).columns


def with_players(path: Path, week_snapshots: list[dict[str, Any]]) -> None:
    write_rows(
        path,
        "leagues",
        [
            {
                "league_key": "t",
                "league_id": LID,
                "season": 2026,
                "current_week": 3,
                "playoff_week_start": 10,
                "roster_positions": ["QB", "RB", "K", "BN", "BN"],
                "scoring_settings": "{}",
            }
        ],
    )
    write_rows(
        path,
        "id_map",
        [{"sleeper_id": "qb1", "gsis_id": "G1"}, {"sleeper_id": "rb1", "gsis_id": "G2"}],
    )
    frame = pl.DataFrame(week_snapshots, schema=store.SCHEMAS["proj_snapshots"])
    store.write_table("proj_snapshots", frame, "archive", path)


def snap(gsis: str, fetched: str, learned: float | None, baseline: float | None) -> dict[str, Any]:
    return {
        "league_id": LID, "gsis_id": gsis, "fetched_at": fetched, "season": 2026, "week": 2,
        "learned": learned, "baseline": baseline,
    }  # fmt: skip


def test_player_vs_projection_uses_the_last_snapshot_and_nulls_a_missing_one(
    league: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_players(
        league,
        [snap("G1", "2026-10-07", 10.0, 9.0), snap("G1", "2026-10-09", 16.0, 14.0)],
    )
    monkeypatch.setattr(store, "projection_name", lambda data_dir=None: "proj_learned")
    out = _digest.player_vs_projection(me_row(league, 3), 2, league)
    got = {r["gsis_id"]: r for r in out.iter_rows(named=True)}
    assert set(got) == {"G1", "G2"}  # starters in skill positions only: no K, no bench
    assert (got["G1"]["points"], got["G1"]["projection"], got["G1"]["diff"]) == (20.0, 16.0, 4.0)
    assert got["G2"]["projection"] is None and got["G2"]["diff"] is None
    assert got["G2"]["points"] == 10.0


def test_player_vs_projection_reads_the_baseline_column_when_configured(
    league: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_players(league, [snap("G1", "2026-10-09", 16.0, 14.0)])
    monkeypatch.setattr(store, "projection_name", lambda data_dir=None: "proj_baseline")
    out = _digest.player_vs_projection(me_row(league, 3), 2, league)
    assert out.filter(pl.col("gsis_id") == "G1")["projection"].to_list() == [14.0]


def test_player_vs_projection_without_snapshots_keeps_points_and_nulls(league: Path) -> None:
    with_players(league, [])
    out = _digest.player_vs_projection(me_row(league, 3), 2, league)
    assert out["projection"].null_count() == out.height == 2


def history(rows: list[tuple[str, int, int, float, float]]) -> pl.DataFrame:
    """(run_at, as_of_week, roster_id, p_playoffs, p_title) rows of one league."""
    return pl.DataFrame(
        [
            {"league_id": LID, "team_name": f"T{r}", "run_at": at, "as_of_week": w, "roster_id": r}
            | {"p_playoffs": po, "p_title": pt}
            for at, w, r, po, pt in rows
        ],
        schema=store.SCHEMAS["sim_season_history"],
    )


def odds_of(table: pl.DataFrame, roster: int = 1) -> dict[str, Any]:
    return (
        _digest.odds_change(table, LID, roster)
        .filter(pl.col("roster_id") == roster)
        .row(0, named=True)
    )


def test_odds_change_compares_to_the_last_run_of_the_nearest_lower_week() -> None:
    table = history(
        [
            ("2026-10-01", 5, 1, 0.50, 0.10),
            ("2026-10-08", 6, 1, 0.55, 0.10),
            ("2026-10-09", 6, 1, 0.60, 0.20),  # a second refresh the same week: this one counts
            ("2026-10-15", 7, 1, 0.70, 0.15),
            ("2026-10-16", 7, 1, 0.80, 0.25),
        ]
    )
    row = odds_of(table)
    assert (row["as_of_week"], row["prev_as_of_week"]) == (7, 6)
    assert row["d_playoffs"] == pytest.approx(0.20) and row["d_title"] == pytest.approx(0.05)


def test_odds_change_is_null_with_one_week_of_history_never_zero() -> None:
    table = history([("2026-10-15", 7, 1, 0.70, 0.15), ("2026-10-16", 7, 1, 0.80, 0.25)])
    row = odds_of(table)
    assert row["prev_as_of_week"] is None
    assert row["d_playoffs"] is None and row["d_title"] is None
    assert row["p_playoffs"] == 0.80  # the latest run of the week


def test_odds_change_nulls_a_team_missing_from_the_earlier_run_and_handles_no_history() -> None:
    table = history([("2026-10-08", 6, 2, 0.5, 0.1), ("2026-10-15", 7, 1, 0.7, 0.2)])
    assert odds_of(table)["d_title"] is None
    assert _digest.odds_change(history([]), LID, 1).is_empty()


def idea_rows(**over: Any) -> list[dict[str, Any]]:
    base = {
        "league_id": LID, "kind": "waiver", "partner": None, "give": "Dropped", "get": "Added",
        "give_ids": ["G9"], "get_ids": ["G8"], "created_at": AT, "as_of_week": 7, "rank": 1,
        "playoff_delta": 0.02, "title_delta": 0.01, "se_title": 0.002, "delta_points": 3.5,
    }  # fmt: skip
    return [
        {**base, **over},
        {**base, "kind": "trade", "partner": "T2", "rank": 1, "delta_points": None},
    ]


def test_move_ideas_filters_by_kind_and_orders_by_rank(league: Path) -> None:
    write_rows(league, "move_ideas", idea_rows())
    out = data_api.move_ideas("t", "waiver", league)
    assert out["get"].to_list() == ["Added"] and out["kind"].to_list() == ["waiver"]
    assert data_api.move_ideas("t", "trade", league)["partner"].to_list() == ["T2"]


def test_move_ideas_are_empty_for_another_team_and_without_the_table(league: Path) -> None:
    assert data_api.move_ideas("t", "waiver", league).is_empty()  # stage never ran
    write_rows(league, "move_ideas", idea_rows())
    with viewing_team(3):
        assert data_api.move_ideas("t", "waiver", league).is_empty()
        assert not data_api.ideas_are_mine("t", league)
    assert data_api.ideas_are_mine("t", league)


def test_stored_waivers_become_the_frame_actions_expects(league: Path) -> None:
    write_rows(league, "move_ideas", idea_rows())
    adds = data_api.stored_adds("t", league)
    assert set(adds.columns) == set(data_api.ENGINE_SCHEMAS["waivers"])
    row = adds.row(0, named=True)
    assert (row["gsis_id"], row["full_name"], row["drop_name"]) == ("G8", "Added", "Dropped")
    assert row["delta_points"] == 3.5 and row["playoff_delta"] == 0.02


def waivers_frame(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "gsis_id": f"G{i}", "full_name": f"Add{i}", "position": "WR",
                "drop_name": f"Drop{i}", "delta_points": 5.0 - i, "playoff_delta": 0.05 - i / 100,
                "title_delta": 0.01, "se_title": 0.002, "trending_adds": None,
            }
            for i in range(n)
        ],
        schema=data_api.ENGINE_SCHEMAS["waivers"],
    )  # fmt: skip


def trades_frame(n: int) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "partner": "T2", "give": f"Give{i} (RB)", "get": f"Get{i} (WR)",
                "give_ids": [f"A{i}"], "get_ids": [f"B{i}"], "kind": "win-win", "my_fills": "WR",
                "their_fills": "RB", "my_fit": 1.0, "their_fit": 1.0, "my_playoff": 0.01 * i,
                "my_title": 0.002, "their_playoff": 0.01, "their_title": 0.0, "se_title": 0.001,
            }
            for i in range(n)
        ]
    )  # fmt: skip


def test_ideas_keep_the_top_waivers_by_playoff_odds_and_the_first_trades() -> None:
    out = stage.ideas(LID, 7, AT, waivers_frame(8), trades_frame(8))
    waiver = out.filter(pl.col("kind") == "waiver")
    trade = out.filter(pl.col("kind") == "trade")
    assert waiver["rank"].to_list() == list(range(1, stage.TOP_WAIVERS + 1))
    assert waiver["get"][0] == "Add0" and waiver["give"][0] == "Drop0"
    assert trade.height == stage.TOP_TRADES and trade["rank"][0] == 1
    assert trade["playoff_delta"][0] == 0.0 and trade["partner"][0] == "T2"
    store.check_schema("move_ideas", out)


def test_ideas_without_trades_write_waivers_only() -> None:
    out = stage.ideas(LID, 7, AT, waivers_frame(1), None)
    assert out["kind"].to_list() == ["waiver"]


def test_run_after_the_deadline_writes_no_trade_rows_and_does_not_fail(league: Path) -> None:
    def past_deadline(league_key: str) -> pl.DataFrame:
        raise ValueError("the trade deadline (week 11) has passed")

    written = stage.run(league, waivers=lambda key: waivers_frame(2), trades=past_deadline, now=AT)
    table = store.read_table("move_ideas", "derived", league)
    assert written == 2 and table["kind"].unique().to_list() == ["waiver"]
    assert table["as_of_week"].unique().to_list() == [3]
    assert table["created_at"].unique().to_list() == [AT]


def test_run_replaces_the_previous_ideas(league: Path) -> None:
    stage.run(
        league, waivers=lambda key: waivers_frame(2), trades=lambda key: trades_frame(1), now=AT
    )
    stage.run(
        league, waivers=lambda key: waivers_frame(1), trades=lambda key: trades_frame(1), now=AT
    )
    assert store.read_table("move_ideas", "derived", league).height == 2


def test_main_logs_and_returns_zero_when_the_stage_breaks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom() -> int:
        raise RuntimeError("no network, no tables")

    monkeypatch.setattr(stage, "run", boom)
    assert stage.main() == 0
