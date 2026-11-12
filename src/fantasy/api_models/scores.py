"""Live score, scoreboard, scorecard and game-day models."""

from typing import Literal

from fantasy.api_models.base import Row


class LiveScoreRow(Row):
    side: str
    team_name: str
    points: float
    projected_final: float


class ScoreboardSide(Row):
    roster_id: int
    team_name: str
    is_me: bool
    projected: float  # expected points to the end of the week
    floor: float  # 10th percentile
    median: float
    ceiling: float  # 90th percentile
    win_prob: float | None  # None for a finished week
    points: float  # scored so far
    share_left: float  # share of the starters games still to play


class ScoreboardRow(Row):
    week: int
    matchup_id: int | None
    status: Literal["Not started", "Live", "Final"]
    a: ScoreboardSide
    b: ScoreboardSide


class ScorecardRow(Row):
    week: int | None  # null = all weeks
    position: str  # "ALL" = every position
    tier: int  # 0 to 2 = projection third, -1 = all
    model: Literal["learned", "baseline", "sleeper"]
    n: int
    mae: float | None
    rmse: float | None
    bias: float | None  # projection minus actual


class ScorecardExcluded(Row):
    games: int
    scored: int
    not_final: int
    no_kickoff: int
    no_snapshot: int
    sleeper_missing: int


class ScorecardData(Row):
    rows: list[ScorecardRow]
    excluded: ScorecardExcluded
    weeks_archived: list[int]
    weeks_scored: list[int]
    sleeper_first_fetch: str | None


class GameDayNow(Row):
    league_id: str
    week: int
    roster_id: int
    my_team: str
    opp_team: str
    win_prob: float  # the existing win probability of the matchup, not a new model
    my_points: float
    opp_points: float
    my_projected: float
    opp_projected: float
    my_left: int  # set starters still to score
    opp_left: int
    points_needed: float  # opponent's projected final minus my points so far


class GameDayPoint(Row):
    league_id: str
    run_at: str
    week: int
    roster_id: int
    win_prob: float
    my_points: float
    opp_points: float
    my_projected: float
    opp_projected: float
    my_left: int
    opp_left: int


class GameDayData(Row):
    week: int | None
    as_of: str | None  # ISO time `current` was computed; the chart's last point
    current: GameDayNow | None
    history: list[GameDayPoint]  # this week's ticks for the viewed team, oldest first
