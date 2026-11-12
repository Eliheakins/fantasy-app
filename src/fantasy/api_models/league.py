"""League list, teams, roster, and the week calendar."""

from fantasy.api_models.base import Row


class LeagueRow(Row):
    league_key: str
    league_id: str
    name: str | None
    current_week: int | None
    playoff_week_start: int | None  # the first week whose seeds are fixed (playoff mode from here)
    playoff_teams: int | None
    num_teams: int | None
    roster_id: int | None
    team_name: str | None
    wins: int | None
    losses: int | None
    ties: int | None
    points_for: float | None
    scoring_labels: str
    record: str
    trade_deadline: int | None


class TeamRow(Row):
    roster_id: int
    team_name: str | None
    wins: int | None
    losses: int | None
    ties: int | None
    points_for: float | None
    is_me: bool
    record: str


class RosterRow(Row):
    sleeper_id: str
    full_name: str | None
    position: str | None
    team: str | None
    injury_status: str | None
    is_starter: bool | None
    is_ir: bool | None


class UnmatchedData(Row):
    count: int
    names: list[str]


class KickoffRow(Row):
    team: str
    kickoff: str | None  # ISO time with the US Eastern offset; null: the schedule has no time


class WaiverClearRow(Row):
    league_key: str
    name: str | None
    day_of_week: int | None  # Sleeper's waiver clear day, 0 is Monday; null when not in the data
    daily: bool  # waivers run every day, so there is no single clear day


class WeekCalendarData(Row):
    week: int | None
    kickoffs: list[KickoffRow]
    waivers: list[WaiverClearRow]


class StatusChangeRow(Row):
    sleeper_id: str
    full_name: str | None
    position: str | None
    team: str | None
    before: str | None  # injury status in the older snapshot; null is healthy
    after: str | None
