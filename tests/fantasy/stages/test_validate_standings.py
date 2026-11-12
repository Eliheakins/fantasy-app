import polars as pl

from fantasy.stages import validate_standings


def team(roster_id: int, wins: int, points_for: float) -> dict[str, object]:
    return {
        "league_id": "L1",
        "roster_id": roster_id,
        "wins": wins,
        "losses": 1 - wins,
        "ties": 0,
        "points_for": points_for,
    }


def test_flagged_counts_a_wrong_record_with_exact_points_as_a_record_mismatch_only() -> None:
    computed = pl.DataFrame([team(1, 1, 100.0), team(2, 0, 90.0)])
    sleeper = pl.DataFrame([team(1, 0, 100.0), team(2, 0, 91.0)])
    flags = validate_standings.flagged(computed, sleeper).sort("roster_id")
    assert flags["record_off"].to_list() == [True, False]
    assert flags["points_off"].to_list() == [False, True]
