"""Lineup holes: a bye, Out or missing starter nobody on the bench covers, with free-agent
fill-ins, and IR moves. The pure logic first, then the read from a tiny store."""

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from store_fixture import write_rows
from test_simulate_load import build_store

from fantasy import _engine, _holes, data_api
from fantasy.sim.availability import EASTERN
from fantasy.sim.bracket import from_rows
from fantasy.sim.lineup import Player

SLOTS = ["QB", "RB", "WR", "TE", "FLEX"]


def names_of(*players: Player) -> dict[str, str]:
    return {p.id: f"name {p.id}" for p in players}


def run(
    starters: list[Player],
    bench: list[Player] | None = None,
    free: list[Player] | None = None,
    *,
    slots: list[str] | None = None,
    out: set[str] | None = None,
    bye: set[str] | None = None,
    startable: set[str] | None = None,
    ros: dict[str, float] | None = None,
) -> list[dict]:
    everyone = [*starters, *(bench or []), *(free or [])]
    return _holes.find_holes(
        _holes.HoleInputs(
            slots=tuple(slots or SLOTS),
            starters=tuple(starters),
            bench=tuple(bench or []),
            free=tuple(free or []),
            out=frozenset(out or ()),
            bye=frozenset(bye or ()),
            startable=frozenset(startable if startable is not None else {p.id for p in everyone}),
            ros=ros or {},
            names=names_of(*everyone),
        )
    )


FULL = [
    Player("qb", "QB", 20.0),
    Player("rb", "RB", 12.0),
    Player("wr", "WR", 11.0),
    Player("te", "TE", 9.0),
    Player("fx", "WR", 8.0),
]


def test_no_hole_when_every_starter_plays() -> None:
    assert run(FULL, [Player("b", "WR", 5.0)]) == []


def test_bye_starter_with_no_cover_is_a_hole_with_fill_ins() -> None:
    free = [Player("f1", "TE", 6.0)]
    [hole] = run(FULL, [], free, bye={"te"})
    assert (hole["kind"], hole["slot"], hole["player_name"]) == ("bye", "TE", "name te")
    assert [f["gsis_id"] for f in hole["fill_ins"]] == ["f1"]
    assert hole["fill_ins"][0]["projection"] == 6.0


def test_bye_starter_with_an_eligible_bench_player_playing_is_covered() -> None:
    assert run(FULL, [Player("b", "TE", 4.0)], bye={"te"}) == []


def test_bench_cover_must_be_eligible_playing_healthy_and_unstarted() -> None:
    bench = [
        Player("wrong", "QB", 9.0),  # not eligible for TE
        Player("hurt", "TE", 9.0),
        Player("bye", "TE", 9.0),
        Player("late", "TE", 9.0),  # game already started
    ]
    holes = run(
        FULL,
        bench,
        bye={"te", "bye"},
        out={"hurt"},
        startable={p.id for p in FULL + bench} - {"late"},
    )
    assert [h["kind"] for h in holes] == ["bye"]


def test_one_bench_player_covers_only_one_hole() -> None:
    holes = run(FULL, [Player("b", "WR", 5.0)], bye={"wr", "fx"})
    assert len(holes) == 1


def test_out_starter_is_a_hole() -> None:
    [hole] = run(FULL, [], out={"qb"})
    assert (hole["kind"], hole["slot"], hole["player_name"]) == ("out", "QB", "name qb")


def test_empty_slot_when_fewer_starters_than_slots() -> None:
    [hole] = run([p for p in FULL if p.id != "te"], [], [Player("f1", "TE", 6.0)])
    assert (hole["kind"], hole["slot"], hole["player_name"]) == ("empty", "TE", None)
    assert [f["gsis_id"] for f in hole["fill_ins"]] == ["f1"]


def test_empty_slot_is_covered_by_a_bench_player() -> None:
    assert run([p for p in FULL if p.id != "te"], [Player("b", "TE", 3.0)]) == []


def test_fill_ins_skip_started_games_and_a_missing_kickoff() -> None:
    free = [Player("started", "TE", 9.0), Player("ok", "TE", 5.0), Player("hurt", "TE", 8.0)]
    startable = {p.id for p in FULL + free} - {"started"}  # no kickoff reads as not startable
    [hole] = run(FULL, [], free, bye={"te"}, startable=startable, out={"hurt"})
    assert [f["gsis_id"] for f in hole["fill_ins"]] == ["ok"]


def test_hole_with_no_unlocked_free_agent_has_no_fill_ins() -> None:
    [hole] = run(FULL, [], [Player("late", "TE", 7.0)], bye={"te"}, startable=set())
    assert hole["fill_ins"] == []


def test_fill_ins_are_the_top_three_eligible_by_this_weeks_projection() -> None:
    free = [Player(f"t{i}", "TE", float(i)) for i in range(1, 6)] + [Player("qb2", "QB", 30.0)]
    [hole] = run(FULL, [], free, bye={"te"})
    assert [f["gsis_id"] for f in hole["fill_ins"]] == ["t5", "t4", "t3"]


def test_drop_is_the_lowest_ros_non_starter() -> None:
    bench = [Player("a", "QB", 1.0), Player("b", "QB", 1.0), Player("c", "QB", 1.0)]
    ros = {"a": 50.0, "b": 10.0, "c": 10.0}
    [hole] = run(FULL, bench, [Player("f", "TE", 6.0)], bye={"te"}, ros=ros)
    assert hole["fill_ins"][0]["drop_name"] == "name b"  # ties go to the lower id


def test_drop_skips_bench_kickers_and_defenses() -> None:
    bench = [Player("d", "DEF", 3.0), Player("k", "K", 2.0), Player("w", "WR", 1.0)]
    [hole] = run(FULL, bench, [Player("f", "TE", 6.0)], bye={"te"}, ros={"w": 5.0})
    assert hole["fill_ins"][0]["drop_name"] == "name w"  # K and DEF have no ros value


def test_drop_is_none_with_an_empty_bench() -> None:
    [hole] = run(FULL, [], [Player("f", "TE", 6.0)], bye={"te"})
    assert hole["fill_ins"][0]["drop_name"] is None


def test_flex_slot_fills_from_rb_wr_te() -> None:
    [hole] = run(FULL, [], [Player("r", "RB", 7.0), Player("q", "QB", 15.0)], bye={"fx"})
    assert (hole["slot"], [f["gsis_id"] for f in hole["fill_ins"]]) == ("FLEX", ["r"])


def test_ir_moves_need_an_open_slot_and_an_eligible_status() -> None:
    bench = {"a": "IR", "b": "Out", "c": "Questionable", "d": "PUP"}
    allowed = frozenset({"IR", "PUP"})
    rows = _holes.ir_moves(bench, 1, allowed, {i: f"name {i}" for i in bench})
    assert [(r["kind"], r["slot"], r["player_name"]) for r in rows] == [("ir_move", "IR", "name a")]
    assert len(_holes.ir_moves(bench, 5, allowed, {i: i for i in bench})) == 2  # a and d only
    assert _holes.ir_moves(bench, 0, allowed, {i: i for i in bench}) == []
    out_ok = frozenset({"IR", "PUP", "Out"})
    assert len(_holes.ir_moves(bench, 5, out_ok, {i: i for i in bench})) == 3


def test_reserve_rules_read_slots_and_allowed_statuses() -> None:
    slots, statuses = _holes.reserve_rules('{"reserve_slots": 2, "reserve_allow_out": 1}')
    assert slots == 2 and statuses == {"IR", "PUP", "Out"}
    off = _holes.reserve_rules('{"reserve_slots": 1, "reserve_allow_out": 0}')
    assert off[1] == {"IR", "PUP"}


def test_reserve_rules_spell_sleepers_statuses() -> None:
    keys = ("out", "doubtful", "sus", "na", "dnr", "cov")
    settings = "{" + ", ".join(f'"reserve_allow_{k}": 1' for k in keys) + "}"
    assert _holes.reserve_rules(settings)[1] == {
        "IR", "PUP", "Out", "Doubtful", "Sus", "NA", "DNR", "COV",
    }  # fmt: skip


@pytest.mark.parametrize("raw", [None, "", "{}", "not json", "[]", '{"reserve_slots": "x"}'])
def test_missing_or_bad_settings_mean_no_ir_slots(raw: str | None) -> None:
    assert _holes.reserve_rules(raw)[0] == 0


# --- the read from a tiny store ---

NOW = datetime(2026, 9, 20, 9, 0, tzinfo=EASTERN)
SEASON = 2026


def _game(home: str, away: str, kickoff: datetime | None) -> dict:
    return {
        "game_type": "REG", "season": SEASON, "week": 3, "home_team": home, "away_team": away,
        "gameday": kickoff.strftime("%Y-%m-%d") if kickoff else None,
        "gametime": kickoff.strftime("%H:%M") if kickoff else None,
    }  # fmt: skip


def holes_store(tmp_path: Path, games: list[dict], settings: str = "{}") -> None:
    build_store(tmp_path, [(100.0, 90.0)])
    leagues = pl.read_parquet(next(tmp_path.rglob("leagues.parquet")))
    write_rows(tmp_path, "leagues", [{**leagues.row(0, named=True), "settings": settings}])
    mine = [("qb", True, False), ("wr", True, False), ("rb", False, False), ("te", False, True)]
    rows = [
        {"league_id": "L1", "roster_id": 1, "sleeper_id": s, "is_starter": st, "is_ir": ir}
        for s, st, ir in mine
    ] + [{"league_id": "L1", "roster_id": 2, "sleeper_id": "opp"}]
    write_rows(tmp_path, "rosters", rows)
    ids = pl.read_parquet(next(tmp_path.rglob("id_map.parquet")))
    ids = ids.with_columns(
        pl.when(pl.col("gsis_id") == "G_FA").then(pl.lit("BUF")).otherwise(pl.col("nfl_team"))
        .alias("nfl_team")
    )  # fmt: skip
    from fantasy import store

    store.write_table("id_map", ids, "derived", tmp_path)
    write_rows(tmp_path, "nfl_schedules", games)


def test_read_bye_hole_lists_free_agent_from_a_team_that_plays(tmp_path: Path) -> None:
    sunday = NOW + timedelta(hours=4)
    holes_store(tmp_path, [_game("BUF", "MIA", sunday), _game("DAL", "NYG", sunday)])
    out = data_api.holes("t", data_dir=tmp_path, now=NOW)
    wr = next(h for h in out if h["slot"] == "WR")
    assert wr["kind"] == "bye"
    assert [f["gsis_id"] for f in wr["fill_ins"]] == ["G_FA"]
    assert wr["fill_ins"][0]["drop_name"] is not None
    assert {h["slot"] for h in out} >= {"QB", "WR"}


def test_read_fill_in_excluded_once_his_game_started(tmp_path: Path) -> None:
    holes_store(tmp_path, [_game("BUF", "MIA", NOW - timedelta(hours=1)), _game("DAL", "NYG", NOW)])
    out = data_api.holes("t", data_dir=tmp_path, now=NOW + timedelta(hours=3))
    assert all(h["fill_ins"] == [] for h in out if h["kind"] != "ir_move")


def test_read_fill_in_excluded_with_a_missing_kickoff(tmp_path: Path) -> None:
    holes_store(tmp_path, [_game("BUF", "MIA", None), _game("DAL", "NYG", NOW)])
    out = data_api.holes("t", data_dir=tmp_path, now=NOW)
    assert out and all(h["fill_ins"] == [] for h in out)


def test_read_out_bench_player_cannot_cover_an_empty_slot(tmp_path: Path) -> None:
    sunday = NOW + timedelta(hours=4)
    holes_store(tmp_path, [_game("KC", "BUF", sunday)])
    out = data_api.holes("t", data_dir=tmp_path, now=NOW)
    assert [(h["kind"], h["slot"]) for h in out] == [("empty", "RB")]  # rb is Out on the bench


def test_read_ir_move_needs_an_open_reserve_slot(tmp_path: Path) -> None:
    sunday = NOW + timedelta(hours=4)
    games = [_game("KC", "BUF", sunday)]
    holes_store(tmp_path, games, '{"reserve_slots": 1, "reserve_allow_out": 1}')
    moves = [h for h in data_api.holes("t", data_dir=tmp_path, now=NOW) if h["kind"] == "ir_move"]
    assert moves == []  # te already fills the only IR slot
    holes_store(tmp_path, games, '{"reserve_slots": 2, "reserve_allow_out": 1}')
    moves = [h for h in data_api.holes("t", data_dir=tmp_path, now=NOW) if h["kind"] == "ir_move"]
    assert [m["player_name"] for m in moves] == ["rb"]
    holes_store(tmp_path, games)  # no settings: no IR slots
    out = data_api.holes("t", data_dir=tmp_path, now=NOW)
    assert [h["kind"] for h in out] == ["empty"]


# --- K and DEF ---

KD_SLOTS = ["QB", "K", "DEF"]
QB = Player("qb", "QB", 20.0)


def test_k_bye_with_no_bench_k_lists_top_three_free_kickers() -> None:
    free = [Player(f"k{i}", "K", float(i)) for i in range(1, 6)]
    [hole] = run([QB, Player("mk", "K", 7.0), Player("d", "DEF", 6.0)], [], free,
                 slots=KD_SLOTS, bye={"mk"})  # fmt: skip
    assert (hole["kind"], hole["slot"]) == ("bye", "K")
    assert [f["gsis_id"] for f in hole["fill_ins"]] == ["k5", "k4", "k3"]


def test_def_out_with_a_bench_def_is_no_hole() -> None:
    starters = [QB, Player("mk", "K", 7.0), Player("d", "DEF", 6.0)]
    assert run(starters, [Player("d2", "DEF", 5.0)], slots=KD_SLOTS, out={"d"}) == []


def test_empty_def_slot_and_started_unit_excluded() -> None:
    free = [Player("late", "DEF", 9.0), Player("ok", "DEF", 4.0), Player("k", "K", 9.0)]
    startable = {"qb", "mk", "ok", "k"}
    [hole] = run([QB, Player("mk", "K", 7.0)], [], free, slots=KD_SLOTS, startable=startable)
    assert (hole["kind"], hole["slot"], hole["player_name"]) == ("empty", "DEF", None)
    assert [f["gsis_id"] for f in hole["fill_ins"]] == ["ok"]


def test_read_k_hole_uses_streaming_projection_for_free_kickers(tmp_path: Path) -> None:
    sunday = NOW + timedelta(hours=4)
    holes_store(tmp_path, [_game("BUF", "MIA", sunday), _game("DAL", "NYG", sunday)])
    leagues = pl.read_parquet(next(tmp_path.rglob("leagues.parquet"))).row(0, named=True)
    write_rows(tmp_path, "leagues", [{**leagues, "roster_positions": ["QB", "RB", "WR", "K"]}])
    rows = [
        {"league_id": "L1", "kind": "K", "unit": u, "team": t, "week": 3, "projection": p}
        for u, t, p in (("G_K", "KC", 6.0), ("G_FREEK", "BUF", 9.0), ("G_THEIRK", "BUF", 12.0))
    ]
    write_rows(tmp_path, "streaming_projection", rows)
    r = pl.read_parquet(next(tmp_path.rglob("rosters.parquet")))
    extra = {"league_id": "L1", "roster_id": 1, "sleeper_id": "kick", "is_starter": True}
    r = pl.concat([r, pl.DataFrame([extra | {"is_ir": False}], schema=r.schema)])
    theirs = {**extra, "roster_id": 2, "sleeper_id": "theirk", "is_ir": False}
    r = pl.concat([r, pl.DataFrame([theirs], schema=r.schema)])
    from fantasy import store

    store.write_table("rosters", r, "raw", tmp_path)
    out = data_api.holes("t", data_dir=tmp_path, now=NOW)
    kicker = next(h for h in out if h["slot"] == "K")
    assert kicker["kind"] == "bye" and kicker["player_name"] == "kick"
    assert [f["gsis_id"] for f in kicker["fill_ins"]] == ["G_FREEK"]  # theirk is rostered


# --- playoff weeks my team does not play ---


def _holes_with(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **over: Any) -> list[dict]:
    sunday = NOW + timedelta(hours=4)
    holes_store(tmp_path, [_game("BUF", "MIA", sunday), _game("DAL", "NYG", sunday)])
    data, mine = _engine._league("t", data_dir=tmp_path)
    monkeypatch.setattr(_holes, "_league", lambda *a, **k: (replace(data, **over), mine))
    return data_api.holes("t", data_dir=tmp_path, now=NOW)


ROUND_ONE_BYE = from_rows(
    [
        {"bracket": "winners", "r": 1, "m": 1, "t1": 3, "t2": 6},
        {"bracket": "winners", "r": 2, "m": 2, "t1": 1, "t2_from_kind": "w", "t2_from_m": 1},
    ]
)


def test_no_holes_in_a_round_one_bye(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _holes_with(tmp_path, monkeypatch, playoff_start=3, bracket=ROUND_ONE_BYE) == []


def test_no_holes_once_the_season_is_over(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert _holes_with(tmp_path, monkeypatch, current_week=18, playoff_start=15) == []


def test_holes_stay_in_a_playoff_game_and_the_regular_season(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    regular = _holes_with(tmp_path, monkeypatch)
    assert regular
    playing = from_rows([{"bracket": "winners", "r": 1, "m": 1, "t1": 1, "t2": 2, "p": 1}])
    assert _holes_with(tmp_path, monkeypatch, playoff_start=3, bracket=playing) == regular


def test_holes_stay_in_a_consolation_game(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    regular = _holes_with(tmp_path, monkeypatch)
    consolation = from_rows(
        [
            {"bracket": "winners", "r": 1, "m": 1, "t1": 2, "t2": 3, "p": 1},
            {"bracket": "losers", "r": 1, "m": 1, "t1": 1, "t2": 4},
        ]
    )
    assert _holes_with(tmp_path, monkeypatch, playoff_start=3, bracket=consolation) == regular


def test_holes_stay_when_my_next_round_slot_is_still_a_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    regular = _holes_with(tmp_path, monkeypatch)
    won_round_one = {"bracket": "winners", "r": 1, "m": 1, "t1": 1, "t2": 6, "w": 1, "l": 6}
    final = {"bracket": "winners", "r": 2, "m": 2, "t1": 3, "t2_from_kind": "w", "t2_from_m": 1}
    advanced = from_rows([won_round_one, final | {"p": 1}])
    assert _holes_with(tmp_path, monkeypatch, playoff_start=2, bracket=advanced) == regular


def test_holes_stay_in_the_playoffs_with_no_bracket_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    regular = _holes_with(tmp_path, monkeypatch)
    assert _holes_with(tmp_path, monkeypatch, playoff_start=3, bracket=()) == regular


@pytest.mark.parametrize(
    ("start", "rows"),
    [
        (2, [  # eliminated in round 1
            {"bracket": "winners", "r": 1, "m": 1, "t1": 1, "t2": 6, "w": 6, "l": 1},
            {"bracket": "winners", "r": 2, "m": 2, "t1": 3, "t2_from_kind": "w", "t2_from_m": 1},
        ]),
        (3, [{"bracket": "winners", "r": 1, "m": 1, "t1": 1, "t2": 2, "p": 1, "w": 1, "l": 2}]),
        (3, [{"bracket": "winners", "r": 1, "m": 1, "t1": 2, "t2": 3, "p": 1}]),  # never in it
    ],
    ids=["eliminated", "champion", "never_in_the_bracket"],
)  # fmt: skip
def test_no_holes_when_out_of_the_bracket_or_champion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, start: int, rows: list[dict[str, Any]]
) -> None:
    assert _holes_with(tmp_path, monkeypatch, playoff_start=start, bracket=from_rows(rows)) == []
