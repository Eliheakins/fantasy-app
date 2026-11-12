"""Lineup, win-probability, action and streamer models."""

from fantasy.api_models.base import Row


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


class SlotCall(Row):
    """Display only: how often this slot's starter outscores the best eligible bench player."""

    slot: str
    starter: str
    alternative: str | None  # None when nobody eligible and unlocked is on the bench
    share: float | None  # of paired simulations; None with no alternative


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
    slot_calls: list[SlotCall]


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
    playoff_label: str | None  # e.g. "Round 2 vs X"; null outside the playoffs
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


class StreamerRow(Row):
    unit: str
    name: str | None
    team: str | None
    is_mine: bool
    this_week: float | None
    next_three: float | None


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
