"""My league rows: one per league with my team, record and scoring labels, and the team lookups.

Package-internal: `data_api` re-exports `leagues` and `scoring_labels`; `_live` and `_calendar` call
`leagues` and `my_league` directly.
"""

import json
from pathlib import Path
from typing import Any

import polars as pl

from fantasy._engine import _read
from fantasy.sim.bracket import playoff_weeks, round_type_of

TEAM_COLUMNS = ["roster_id", "team_name", "wins", "losses", "ties", "points_for"]


def scoring_labels(scoring: dict[str, float], roster_positions: list[str]) -> list[str]:
    labels = [f"{scoring.get('rec', 0):g} PPR", f"{scoring.get('pass_td', 0):g}-pt pass TD"]
    if scoring.get("pass_int"):
        labels.append(f"{scoring['pass_int']:g} per INT")
    if "SUPER_FLEX" in roster_positions:
        labels.append("Superflex")
    return labels


def leagues(data_dir: Path | None = None) -> pl.DataFrame:
    """One row per league with my team, record and scoring labels."""
    mine = _read("league_teams", data_dir).filter(pl.col("is_me"))
    joined = _read("leagues", data_dir).join(mine, on="league_id", how="left")
    labels = [
        ", ".join(scoring_labels(json.loads(scoring), positions))
        for scoring, positions in zip(
            joined["scoring_settings"], joined["roster_positions"], strict=True
        )
    ]
    lengths = [
        playoff_weeks(int(teams), round_type_of(settings)) if teams else None
        for teams, settings in zip(joined["playoff_teams"], joined["settings"], strict=True)
    ]
    return joined.with_columns(
        pl.Series("scoring_labels", labels, dtype=pl.String),
        pl.Series("playoff_weeks", lengths, dtype=pl.Int64),
    ).select(
        "league_key",
        "league_id",
        "name",
        "current_week",
        "playoff_week_start",
        "playoff_teams",
        "playoff_weeks",
        "num_teams",
        "roster_id",
        "team_name",
        "wins",
        "losses",
        "ties",
        "points_for",
        "scoring_labels",
    )


def my_league(
    league_key: str, data_dir: Path | None, team: int | None = None
) -> dict[str, Any] | None:
    """My row in `leagues` for a league key (the `team` roster's if given), or None if the league
    is not there."""
    rows = leagues(data_dir).filter(pl.col("league_key") == league_key)
    if rows.is_empty():
        return None
    row = rows.row(0, named=True)
    return row if team is None else {**row, **team_fields(row["league_id"], team, data_dir)}


def team_fields(league_id: str, roster_id: int, data_dir: Path | None) -> dict[str, Any]:
    """The `leagues` columns that describe a team, for the team being viewed."""
    team = _read("league_teams", data_dir).filter(
        (pl.col("league_id") == league_id) & (pl.col("roster_id") == roster_id)
    )
    if team.is_empty():
        raise ValueError(f"unknown team {roster_id} in league {league_id!r}")
    return team.select(TEAM_COLUMNS).row(0, named=True)
