"""A team's next unplayed NFL game, or its bye: opponent, home or away, kickoff."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import polars as pl

from fantasy import store
from fantasy._engine import _id_map
from fantasy.config import load_config
from fantasy.sim.availability import EASTERN


@dataclass(frozen=True)
class NextGame:
    week: int
    opponent: str | None  # None on a bye
    home: bool
    kickoff: datetime | None  # US Eastern, None when the schedule has no time yet

    def short(self) -> str:
        """The opponent for a table cell: "vs KC", "@ KC" or "Bye"."""
        if self.opponent is None:
            return "Bye"
        return f"{'vs' if self.home else '@'} {self.opponent}"

    def long(self) -> str:
        """A sentence fragment: "Week 10 at KC, Sun 1:00 PM ET" or "Week 10 bye"."""
        if self.opponent is None:
            return f"Week {self.week} bye"
        when = (
            f", {self.kickoff:%a} {self.kickoff:%I:%M %p}".replace(" 0", " ") + " ET"
            if self.kickoff
            else ""
        )
        return f"Week {self.week} {'vs' if self.home else 'at'} {self.opponent}{when}"


def next_games_by_team(
    schedules: pl.DataFrame, season: int, current_week: int
) -> dict[str, NextGame]:
    """Each team's first game from `current_week` on that has no score yet. A team with no game
    in `current_week` at all is on a bye, shown as that week; a team done for the season has none.
    """
    games = schedules.filter((pl.col("season") == season) & (pl.col("week") >= current_week)).sort(
        "week", "gameday", "gametime"
    )
    columns = ("week", "gameday", "gametime", "away_team", "home_team", "away_score", "home_score")
    out: dict[str, NextGame] = {}
    plays_this_week: set[str] = set()
    for week, day, time, away, home, away_score, home_score in games.select(columns).iter_rows():
        if week == current_week:
            plays_this_week |= {away, home}
        if away_score is not None and home_score is not None:
            continue
        kickoff = (
            datetime.fromisoformat(f"{day}T{time}").replace(tzinfo=EASTERN)
            if day and time
            else None
        )
        for team, opponent, is_home in ((home, away, True), (away, home, False)):
            out.setdefault(team, NextGame(week, opponent, is_home, kickoff))
    return {
        team: NextGame(current_week, None, False, None)
        if team not in plays_this_week and game.week > current_week
        else game
        for team, game in out.items()
    }


def next_games(
    gsis_ids: list[str], current_week: int, data_dir: Path | None = None
) -> dict[str, NextGame]:
    """`next_games_by_team` for the NFL teams of these players, keyed by nflverse id."""
    by_team = next_games_by_team(
        store.read_table("nfl_schedules", "raw", data_dir), load_config().season, current_week
    )
    teams = _id_map(data_dir, "nfl_team").filter(pl.col("gsis_id").is_in(gsis_ids))
    return {
        g: by_team[t]
        for g, t in zip(teams["gsis_id"], teams["nfl_team"], strict=True)
        if t in by_team
    }


def bye_week_of(schedules: pl.DataFrame, season: int, team: str) -> int | None:
    """The week `team` has no game, between its first and last game of the season."""
    games = schedules.filter(
        (pl.col("season") == season)
        & ((pl.col("home_team") == team) | (pl.col("away_team") == team))
    )
    played = set(games["week"].to_list())
    return (
        next((w for w in range(min(played), max(played)) if w not in played), None)
        if played
        else None
    )


def bye_week(gsis_id: str, data_dir: Path | None = None) -> int | None:
    """The bye week of this player's NFL team."""
    teams = _id_map(data_dir, "nfl_team").filter(pl.col("gsis_id") == gsis_id)["nfl_team"]
    if teams.is_empty() or teams[0] is None:
        return None
    schedules = store.read_table("nfl_schedules", "raw", data_dir)
    return bye_week_of(schedules, load_config().season, teams[0])
