from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import polars as pl

from fantasy import data_api, store
from fantasy.sim.availability import kickoffs, locked_teams
from fantasy.sim.lineup import Player
from fantasy.stages import validate_scoring, validate_standings

SCORING = {"pass_td": 4.0}


def stats_row(player_id: str, passing_tds: float) -> pl.DataFrame:
    schema = store.SCHEMAS["nfl_player_stats"]
    row = {c: 0.0 if t == pl.Float64 else None for c, t in schema.items()}
    row |= {"player_id": player_id, "passing_tds": passing_tds}
    return pl.DataFrame([row], schema=schema)


def compare(sleeper_points: list[tuple[str, float, str]], computed_tds: float) -> pl.DataFrame:
    ids = [s for s, _, _ in sleeper_points]
    return validate_scoring.compare_league(
        SCORING,
        pl.DataFrame(
            {"sleeper_id": ids, "points": [p for _, p, _ in sleeper_points]},
        ),
        pl.DataFrame({"sleeper_id": ids, "gsis_id": [f"G{s}" for s in ids]}),
        pl.DataFrame(
            {"sleeper_id": ids, "full_name": ids, "position": [pos for _, _, pos in sleeper_points]}
        ),
        stats_row("G1", computed_tds),
    )


def test_compare_league_diff_is_zero_when_sleeper_and_ours_agree() -> None:
    out = compare([("1", 8.0, "QB")], computed_tds=2.0)
    assert out["diff"].to_list() == [0.0]


def test_compare_league_flags_a_player_whose_points_differ() -> None:
    out = compare([("1", 8.0, "QB")], computed_tds=3.0)
    assert out["diff"].to_list() == [4.0]
    assert out.filter(pl.col("diff").abs() > validate_scoring.TOLERANCE).height == 1


def test_compare_league_skips_defenses_and_scores_a_player_without_stats_as_zero() -> None:
    out = compare([("1", 8.0, "DEF"), ("2", 5.0, "WR")], computed_tds=2.0)
    assert out["sleeper_id"].to_list() == ["2"]
    assert out["computed"].to_list() == [0.0] and out["diff"].to_list() == [-5.0]


def record(roster_id: int, wins: int, points_for: float) -> dict:
    return {
        "league_id": "L1",
        "roster_id": roster_id,
        "wins": wins,
        "losses": 1 - wins,
        "ties": 0,
        "points_for": points_for,
    }


def test_standings_compare_passes_when_records_and_points_match() -> None:
    rows = [record(1, 1, 100.0), record(2, 0, 90.0)]
    out = validate_standings.compare(pl.DataFrame(rows), pl.DataFrame(rows))
    assert out.is_empty()


def test_standings_compare_flags_a_wrong_record_or_points_and_a_missing_team() -> None:
    computed = pl.DataFrame([record(1, 1, 100.0), record(2, 0, 90.0), record(3, 0, 80.0)])
    sleeper = pl.DataFrame([record(1, 0, 100.0), record(2, 0, 91.0)])
    out = validate_standings.compare(computed, sleeper)
    assert sorted(out["roster_id"].to_list()) == [1, 2, 3]


def test_standings_compare_allows_rounding_within_the_points_tolerance() -> None:
    computed = pl.DataFrame([record(1, 1, 100.0)])
    sleeper = pl.DataFrame([record(1, 1, 100.01)])
    assert validate_standings.compare(computed, sleeper).is_empty()


SCHEDULE_COLUMNS = ["season", "week", "gameday", "gametime", "away_team", "home_team"]


def games(*rows: tuple[int, int, str | None, str | None, str, str]) -> pl.DataFrame:
    return pl.DataFrame(list(rows), schema=SCHEDULE_COLUMNS, orient="row")


def test_kickoffs_omit_a_game_with_no_date_or_time_without_raising() -> None:
    schedule = games(
        (2026, 7, None, "13:00", "A", "B"),
        (2026, 7, "2026-10-25", None, "C", "D"),
        (2026, 7, "2026-10-25", "13:00", "E", "F"),
        (2026, 8, "2026-11-01", "13:00", "G", "H"),
    )
    assert set(kickoffs(schedule, 2026, 7)) == {"E", "F"}
    assert locked_teams(schedule, 2026, 7, datetime(2027, 1, 1, tzinfo=UTC)) == {"E", "F"}


def test_one_pm_eastern_kickoff_is_17_utc_in_edt_and_18_utc_in_est() -> None:
    schedule = games(
        (2026, 7, "2026-10-25", "13:00", "A", "B"),  # EDT, UTC-4
        (2026, 12, "2026-11-29", "13:00", "C", "D"),  # EST, UTC-5
    )
    edt = kickoffs(schedule, 2026, 7)["A"].astimezone(ZoneInfo("UTC"))
    est = kickoffs(schedule, 2026, 12)["C"].astimezone(ZoneInfo("UTC"))
    assert edt == datetime(2026, 10, 25, 17, 0, tzinfo=UTC)
    assert est == datetime(2026, 11, 29, 18, 0, tzinfo=UTC)


EDGES = {"WR": [5.0, 10.0]}


def test_tier_puts_a_value_exactly_on_an_edge_in_the_lower_tier() -> None:
    tiers = [data_api._tier(EDGES, Player("x", "WR", v)) for v in (4.99, 5.0, 5.01, 10.0, 10.01)]
    assert tiers == [0, 0, 1, 1, 2]


def test_tier_is_minus_one_for_a_position_with_no_edges() -> None:
    assert data_api._tier(EDGES, Player("x", "QB", 12.0)) == -1


def test_tier_edges_need_both_tiers_and_use_the_projection_ceiling() -> None:
    schema = store.SCHEMAS["marginals"]
    rows = [
        {"position": "WR", "tier": 0, "proj_max": 5.0},
        {"position": "WR", "tier": 1, "proj_max": 10.0},
        {"position": "RB", "tier": 0, "proj_max": 4.0},
    ]
    blank = dict.fromkeys(schema)
    frame = pl.DataFrame([{**blank, **r} for r in rows], schema=schema)
    assert data_api._tier_edges(frame) == {"WR": [5.0, 10.0]}
