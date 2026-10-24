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


class StatusData(Row):
    freshness: list[FreshnessRow]
    missing_layers: list[str]
    simulation_behind_inputs: str | None
    data_version: str


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


class TradeEvaluation(Row):
    odds: list[TradeSideRow]
    roster_changes: list[RosterChangeRow]
    warning: str | None
    trade_deadline: int | None


class FoundTradeRow(Row):
    partner: str
    give: str
    get: str
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
