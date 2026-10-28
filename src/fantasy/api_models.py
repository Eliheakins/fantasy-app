"""Response models for the API. `extra="forbid"` makes a drifting data_api column fail loudly in
the smoke tests instead of silently disappearing from the OpenAPI schema."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class Row(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiError(Row):
    code: Literal["no_data", "invalid", "busy", "server"]
    message: str


class Envelope[T](Row):
    status: Literal["ok", "running", "error"]
    data: T | None
    error: ApiError | None
    started_at: str | None  # set while a job is running


class FreshnessRow(Row):
    source: str
    updated_at: datetime
    age_hours: float


class LiveRefreshData(Row):
    enabled: bool
    active: bool  # a game of the current week is on now
    last_ok_at: str | None  # ISO time of the last good live tick
    last_error: str | None
    interval_minutes: int


class StatusData(Row):
    freshness: list[FreshnessRow]
    missing_layers: list[str]
    simulation_behind_inputs: str | None
    data_version: str
    live_refresh: LiveRefreshData


class LeagueRow(Row):
    league_key: str
    league_id: str
    name: str | None
    current_week: int | None
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


class StreamerRow(Row):
    unit: str
    name: str | None
    team: str | None
    is_mine: bool
    this_week: float | None
    next_three: float | None


class LineupRow(Row):
    slot: str
    gsis_id: str
    full_name: str
    position: str
    projection: float
    p10: float | None
    p90: float | None
    starting_now: bool
    recommended: bool
    injury: str | None
    injury_note: str | None
    locked: bool
    actual: float
    game: str
    change: str
    swap_in: str | None = None  # bench player to start if this flagged starter is inactive


class ScheduleRow(Row):
    week: int
    opponent: str
    my_points: float
    their_points: float
    win_chance: float


class StrengthRow(Row):
    position: str
    vor_per_week: float
    rank: int
    teams: int


class LiveScoreRow(Row):
    side: str
    team_name: str
    points: float
    projected_final: float


class PartnerRow(Row):
    roster_id: int
    team_name: str


class AssetRow(Row):
    gsis_id: str
    full_name: str
    position: str
    ros_points: float
    label: str


class MarketValueRow(Row):
    gsis_id: str
    value: float
    overall_rank: int | None
    position_rank: int | None
    trend_30_day: float | None
    fetched_at: str


class PlayerWeekRow(Row):
    week: int
    projection: float


class OutlookRow(Row):
    gsis_id: str
    full_name: str
    position: str
    owner: str
    recent_ppg: float | None
    expected_ppg: float | None
    next_ppg: float | None
    change: float | None
    chance_to_play: float | None
    label: str
    why: str


class OptionRow(Row):
    option: str
    win_prob: float
    expected_points: float
    gsis_ids: list[str]
    slots: list[str]
    share_better: float
    tag: str
    floor: float
    median: float
    ceiling: float
    opp_floor: float
    opp_median: float
    opp_ceiling: float
    script: str


class ComparisonRow(Row):
    option: str
    win_prob: float
    expected_points: float
    floor: float
    median: float
    ceiling: float


class SwapNoteModel(Row):
    differs: bool
    players_in: list[str]
    players_out: list[str]
    text: str | None


class SummaryModel(Row):
    objective: str
    shown_points: float
    sleeper_points: float | None
    gap: float | None
    win_prob: float | None


class WinProbabilityData(Row):
    script: str | None
    swap: SwapNoteModel | None
    comparison: list[ComparisonRow]
    options: list[OptionRow]
    lineups: dict[str, list[LineupRow]]  # keyed by objective, rows re-slotted for it
    summaries: dict[str, SummaryModel]


class ActionRow(Row):
    kind: str
    text: str
    delta_points: float | None = None
    share_better: float | None = None


class WaiverRow(Row):
    gsis_id: str
    full_name: str
    position: str
    drop_name: str
    delta_points: float
    playoff_delta: float | None
    title_delta: float | None
    se_title: float | None
    trending_adds: int | None


class TradeSideRow(Row):
    side: str
    roster_id: int
    team_name: str
    playoff_before: float
    playoff_after: float
    title_before: float
    title_after: float
    wins_before: float
    wins_after: float


class RosterChangeRow(Row):
    team_name: str
    action: str
    full_name: str
    position: str


class MarketSummary(Row):
    """Market value each side gives and gets (FantasyCalc), the hint and the values' date."""

    give_value: float
    get_value: float
    hint: str
    fetched_at: str
    accepted_share: float | None = None  # share of past accepted trades this lopsided or worse
    accepted_sides: int = 0  # past accepting sides the share is out of


class TradeEvaluation(Row):
    odds: list[TradeSideRow]
    roster_changes: list[RosterChangeRow]
    warning: str | None
    trade_deadline: int | None
    market: MarketSummary | None


class FoundTradeRow(Row):
    partner: str
    give: str
    get: str
    give_ids: list[str]
    get_ids: list[str]
    kind: Literal["win-win", "need swap"]
    my_fills: str
    their_fills: str
    my_fit: float
    their_fit: float
    market: MarketSummary | None
    my_playoff: float
    my_title: float
    their_playoff: float
    their_title: float
    se_title: float


MAX_TRADE_IDS, MAX_ID_LENGTH = 10, 64
TradeIds = Annotated[
    list[Annotated[str, Field(max_length=MAX_ID_LENGTH)]],
    Field(min_length=1, max_length=MAX_TRADE_IDS),
]


class TradeRequest(BaseModel):
    partner_roster_id: int
    give_ids: TradeIds
    get_ids: TradeIds


class RefreshData(Row):
    player_rows: int


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
    has_quantiles: bool  # false: snapshots hold means only, so no interval coverage
    sleeper_first_fetch: str | None


class LastWeekRow(Row):
    week: int
    roster_id: int
    team_name: str
    opponent: str | None
    points: float
    opp_points: float
    result: Literal["W", "L", "T"]
    bench_points_left: float | None  # null: unknown (playoff week, no player rows), not zero
    luck: float | None  # wins above what the all-play record predicts, that week only


class ProjectionMissRow(Row):
    gsis_id: str
    full_name: str | None
    position: str
    points: float | None
    projection: float | None  # null where proj_snapshots has no row for the player
    diff: float | None


class OddsChangeRow(Row):
    roster_id: int
    team_name: str
    is_me: bool
    as_of_week: int
    prev_as_of_week: int | None
    p_playoffs: float | None
    p_title: float | None
    d_playoffs: float | None  # null without an earlier week, never zero
    d_title: float | None


class MoveIdeaRow(Row):
    kind: Literal["waiver", "trade"]
    partner: str | None
    give: str
    get: str
    give_ids: list[str]
    get_ids: list[str]
    rank: int
    playoff_delta: float | None
    title_delta: float | None
    se_title: float | None
    delta_points: float | None


class IdeasInfo(Row):
    is_mine: bool  # ideas are stored for my team only; false means the lists are empty by design
    created_at: str | None  # when the digest stage ran
    as_of_week: int | None
    current_week: int | None
    trade_deadline: int | None
    deadline_passed: bool


class WatchRow(Row):
    gsis_id: str
    full_name: str
    position: str
    ros_points: float
    reasons: list[str]


class DigestData(Row):
    last_week: LastWeekRow | None  # null in week 1
    performance: list[ProjectionMissRow]
    watch: list[WatchRow]
    odds_change: list[OddsChangeRow]
    waivers: list[MoveIdeaRow]
    trades: list[MoveIdeaRow]
    ideas: IdeasInfo
