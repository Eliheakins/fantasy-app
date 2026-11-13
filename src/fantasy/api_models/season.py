"""Season odds and the league-wide season tables."""

from typing import Literal

from fantasy.api_models.base import Row


class BracketSide(Row):
    roster_id: int | None  # null until an earlier match decides it
    team_name: str | None
    seed: int | None
    from_kind: str | None  # "w" or "l": the side is the winner or loser of match from_m
    from_m: int | None


class BracketMatch(Row):
    m: int
    place: int | None  # placement the winner takes (1 title, 3, 5); null on the way to the final
    winner: int | None  # roster id once played
    t1: BracketSide
    t2: BracketSide
    t1_p_win: float | None  # chance to win this round; null when played or a placement game
    t2_p_win: float | None
    is_mine: bool


class BracketRound(Row):
    round: int
    weeks: list[int]
    matches: list[BracketMatch]


class BracketData(Row):
    rounds: list[BracketRound]


class SeasonOddsRow(Row):
    roster_id: int
    team_name: str
    p_playoffs: float | None
    p_bye: float | None
    p_title: float | None
    exp_wins: float | None
    is_me: bool


class SeedRow(Row):
    seed: int
    p: float


class OddsHistoryRow(Row):
    run_at: str
    team_name: str
    roster_id: int
    p_playoffs: float | None
    p_title: float | None
    as_of_week: int | None


class PowerRankingRow(Row):
    roster_id: int
    team_name: str
    is_me: bool
    rank: int | None
    exp_points_week: float | None
    exp_wins: float | None
    p_playoffs: float | None
    p_title: float | None
    sos_remaining: float | None
    sos_rank: int | None


class TeamGradeRow(Row):
    roster_id: int
    team_name: str
    is_me: bool
    position: str
    vor_per_week: float
    depth_per_week: float
    score: float
    rank: int
    grade: str


class LuckRow(Row):
    roster_id: int
    team_name: str
    is_me: bool
    weeks: int
    wins: int
    losses: int
    ties: int
    ap_wins: int
    ap_losses: int
    ap_ties: int
    exp_wins: float
    luck: float


class ManagerGradeRow(Row):
    roster_id: int
    team_name: str
    is_me: bool
    weeks: int
    actual_points: float
    optimal_points: float
    efficiency: float
    bench_points_left: float


class WhatIfRow(Row):
    winner_id: int
    loser_id: int
    winner: str
    loser: str
    involves_me: bool
    p_condition: float
    n_runs: int
    d_playoffs: float
    d_title: float


class WinNeedRow(Row):
    n_games: int
    wins: int
    n_runs: int
    p_condition: float
    p_playoffs: float


class SeasonEventRow(Row):
    kind: Literal["trade", "injury", "big_week"]
    when: str
    run_at: str | None  # the saved run that first reflects it; null before the first run
    label: str
