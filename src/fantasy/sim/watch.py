"""Facts that put one of my players on the drop-risk watch. These are alerts, not forecasts: the
projection already uses snaps and injuries, and nothing here is tested to predict a miss."""

ROLE_WINDOW = 3  # games in the recent stretch
MIN_PRIOR_GAMES = 2  # games before it needed for a comparison
ROLE_DROP = 0.15  # fall in offensive snap share (a fraction of snaps) that counts
MARKET_DROP = 0.15  # fall in market value over 30 days, as a share of the value 30 days ago
MARKET_MIN_VALUE = 500.0  # below this FantasyCalc values move too much to read


def role_drop(snap_shares: list[float]) -> tuple[float, float] | None:
    """(share before, share lately) when the last ROLE_WINDOW games average at least ROLE_DROP
    below the games before them. `snap_shares` is one offensive snap share per game, oldest
    first, for games the player was on the field."""
    if len(snap_shares) < ROLE_WINDOW + MIN_PRIOR_GAMES:
        return None
    recent = snap_shares[-ROLE_WINDOW:]
    prior = snap_shares[:-ROLE_WINDOW][-ROLE_WINDOW:]
    before, lately = sum(prior) / len(prior), sum(recent) / len(recent)
    return (before, lately) if before - lately >= ROLE_DROP else None


def market_drop(value: float | None, trend_30_day: float | None) -> float | None:
    """Fall in market value over 30 days as a share of the value then, if at least MARKET_DROP."""
    if value is None or trend_30_day is None:
        return None
    then = value - trend_30_day
    if value < MARKET_MIN_VALUE or then <= 0:
        return None
    fall = -trend_30_day / then
    return fall if fall >= MARKET_DROP else None
