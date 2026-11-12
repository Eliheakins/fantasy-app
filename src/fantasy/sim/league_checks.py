"""Checks on a league's stored tables while `load_league_data` builds it.

What the simulation drops or cannot model is reported here: `report` warns about it, and raises
when more than a limit were dropped and the caller is strict (the stage; the dashboard is not).
"""

import warnings
from typing import Any

import polars as pl

from fantasy.sim.bracket import row_problem

MAX_NO_PROJECTION = 3  # rostered skill players with no projection at all, per league


def report(problem: str, names: list[str], limit: int, lid: str, strict: bool = True) -> None:
    """Warn about what was dropped for `lid`; stop the stage when more than `limit` were. The
    dashboard passes strict=False: a few unprojected rookies should not blank a league's page."""
    if not names:
        return
    message = f"league {lid}: {len(names)} {problem}: {sorted(names)}"
    if strict and len(names) > limit:
        raise RuntimeError(f"{message} (limit {limit})")
    warnings.warn(message, stacklevel=3)


def check_projected(
    rosters: pl.DataFrame, projections: pl.DataFrame, lid: str, strict: bool = True
) -> None:
    """Rostered players with no projection in any remaining week are left out of their team's
    lineup and replaced by a free agent, which silently weakens the team."""
    projected = set(projections["gsis_id"].to_list())
    missing = [g for g in rosters["gsis_id"].unique(maintain_order=True) if g not in projected]
    report("rostered skill players with no projection", missing, MAX_NO_PROJECTION, lid, strict)


def check_standings(base: pl.DataFrame, teams: pl.DataFrame, lid: str) -> None:
    """The recomputed win-loss-tie record should match Sleeper's; a mismatch means phantom ties
    or missing weeks in the matchups table. Points are not compared (Sleeper's differ by a point
    or two in one league, see validate_standings). Skipped when Sleeper's record is not stored."""
    record = ["wins", "losses", "ties"]
    if not set(record) <= set(teams.columns):
        return
    joined = base.join(teams.select("roster_id", *record), on="roster_id", suffix="_sleeper")
    bad = joined.filter(pl.any_horizontal(*(pl.col(c) != pl.col(f"{c}_sleeper") for c in record)))
    if bad.height:
        warnings.warn(
            f"league {lid}: recomputed records differ from Sleeper's for rosters "
            f"{sorted(bad['roster_id'].to_list())}; run validate_standings",
            stacklevel=2,
        )


def check_league_shape(league: dict[str, Any]) -> None:
    """Raise for a league the bracket model cannot fit, by the same gate as `format_problem`.
    A league with no playoff teams recorded is left to that gate (the stage skips it)."""
    if league.get("playoff_teams") is None:
        return
    problem = row_problem(league)
    if problem:
        raise ValueError(f"league {league['league_id']}: {problem}")
