"""Player pages: market values, points, profile, outlook, owners."""

from fantasy.api_models.base import Row


class MarketValueRow(Row):
    gsis_id: str
    value: float
    overall_rank: int | None
    position_rank: int | None
    trend_30_day: float | None
    fetched_at: str


class MarketHistoryRow(Row):
    day: str
    value: float


class PlayerPointsRow(Row):
    gsis_id: str
    week: int
    points: float


class PlayerWeekRow(Row):
    week: int
    projection: float


class RoleWeek(Row):
    week: int
    snap_share: float | None
    target_share: float | None


class PlayerProfile(Row):
    """Display only: next game range, rest of season over replacement, injury, outlook."""

    gsis_id: str
    full_name: str | None
    position: str | None
    week: int | None  # the week the range is for: this week, or the next with a projection
    result_week: int | None  # this week, when the player's game is already final
    result_points: float | None
    projection: float | None
    p10: float | None
    median: float | None
    p90: float | None
    chance_to_play: float | None
    injury: str | None
    injury_note: str | None
    is_out: bool
    ros_points: float | None
    replacement_name: str | None
    replacement_points: float | None
    ros_over_replacement: float | None
    outlook_label: str | None
    why: str | None
    role_weeks: list[RoleWeek]
    next_game: str | None  # "Week 10 at KC, Sun 1:00 PM ET" or "Week 10 bye"
    bye_week: int | None


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
    next_game: str | None  # "vs KC", "@ KC" or "Bye"
    label: str
    why: str


class OwnerRow(Row):
    gsis_id: str
    owner: str
    roster_id: int
    is_mine: bool


class OwnersData(Row):
    rows: list[OwnerRow]
    unmatched: int
