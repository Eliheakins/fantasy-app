"""Roster value measured over a replacement-level floor.

Every lineup slot can always be filled by a stand-in free agent: not the best ones on the wire
(those are adds you would have to claim and hold) but the next few, which anyone can stream. So
a player is worth what he adds over that floor, and a backup tight end is nearly worthless when
tight ends of that quality sit on waivers, while a position with no good free agents makes depth
matter. Bye weeks and injuries are filled the same way: the slot falls back to a stand-in.

Stand-ins are free agents ranked REPLACEMENT_SKIP + 1 and lower at each position (the top few
are what a waiver add would be). Absences are first-order: each starter is considered out on his
own. Shortcut: stand-ins are assumed available and picked up in time; players a team drops are
not assumed available, since someone else will claim them.
"""

import polars as pl

from fantasy.sim.lineup import Player, auto_lineup

POSITIONS = ("QB", "RB", "WR", "TE")
REPLACEMENT_SKIP = 2  # the best free agents are adds, not stand-ins
REPLACEMENT_DEPTH = 6  # stand-in candidates kept per position and week
STAND_INS_PER_POSITION = 2  # used per position and week, after dropping the roster's own


def play_curves(projections: pl.DataFrame, weeks: list[int]) -> dict[str, tuple[float, ...]]:
    """Each flagged player's chance of playing in each of `weeks`, trimmed after his last week
    below 1. After the curve the absence chain carries on from where it left off. Players with
    no `play_prob` below 1 are left out: they follow the default chain. Weeks without a row (a
    bye) count as 1.0."""
    if "play_prob" not in projections.columns:
        return {}
    by_player: dict[str, dict[int, float]] = {}
    for g, w, p in projections.select("gsis_id", "week", "play_prob").iter_rows():
        by_player.setdefault(g, {})[w] = p
    curves = {}
    for g, chance in by_player.items():
        probs = [chance.get(w, 1.0) for w in weeks]
        last = max((i for i, p in enumerate(probs) if p < 1.0), default=-1)
        if last >= 0:
            curves[g] = tuple(probs[: last + 1])
    return curves


def absence_probs(
    curve: tuple[float, ...], n_weeks: int, hazard: float, stay_out: float
) -> list[float]:
    """Chance a player is out in each of the next n_weeks: from his curve while it lasts (a
    healthy player's curve is (1.0,)), then the two-state chain used by the season simulation."""
    if n_weeks <= 0 or not curve:
        return []
    out = [1.0 - p for p in curve[:n_weeks]]
    q = out[-1]
    while len(out) < n_weeks:
        q = q * stay_out + (1.0 - q) * hazard
        out.append(q)
    return out


def values_by_week(frame: pl.DataFrame) -> dict[int, dict[str, float]]:
    """`frame` (gsis_id, week, projection) as {week: {gsis_id: projection}}."""
    return {
        week: dict(zip(g["gsis_id"], g["projection"], strict=True))
        for (week,), g in frame.group_by("week")
    }


def conditional_values(projections: pl.DataFrame) -> dict[int, dict[str, float]]:
    """Expected points when the player plays: projection over his chance of playing (0 when he
    cannot play), by week. Without a `play_prob` column the projection is already that."""
    frame = projections
    if "play_prob" in frame.columns:
        frame = frame.with_columns(
            pl.when(pl.col("play_prob") > 0)
            .then(pl.col("projection") / pl.col("play_prob"))
            .otherwise(0.0)
            .alias("projection")
        )
    return values_by_week(frame)


def replacement_pool(
    free_ids: list[str], positions: dict[str, str], values_by_week: dict[int, dict[str, float]]
) -> dict[int, list[Player]]:
    """Stand-in candidates per week: at each position the free agents ranked just below the
    top REPLACEMENT_SKIP, best first."""
    pool: dict[int, list[Player]] = {}
    for week, values in values_by_week.items():
        chosen: list[Player] = []
        for position in POSITIONS:
            ranked = sorted(
                (i for i in free_ids if positions.get(i) == position and values.get(i, 0.0) > 0),
                key=lambda i: (-values[i], i),
            )
            start = REPLACEMENT_SKIP
            chosen += [
                Player(i, position, values[i]) for i in ranked[start : start + REPLACEMENT_DEPTH]
            ]
        pool[week] = chosen
    return pool


def stand_ins(candidates: list[Player], mine: set[str]) -> list[Player]:
    """The stand-ins in use: per position the first few candidates the roster does not hold."""
    out: list[Player] = []
    for position in POSITIONS:
        free = [p for p in candidates if p.position == position and p.id not in mine]
        out += free[:STAND_INS_PER_POSITION]
    return out


def season_value(
    slots: list[str],
    positions: dict[str, str],
    values_by_week: dict[int, dict[str, float]],
    ids: list[str],
    absence: dict[str, list[float]],
    replacements: dict[int, list[Player]],
) -> float:
    """Expected points over the weeks in `values_by_week`, counting absences and replacements.

    `absence[id]` lists the chance the player is out in each week, in week order; players
    without an entry are treated as healthy."""
    mine = set(ids)
    total = 0.0
    for index, (week, values) in enumerate(sorted(values_by_week.items())):
        pool = [Player(i, positions[i], values[i]) for i in ids if i in values and i in positions]
        floor = stand_ins(replacements.get(week, []), mine)
        lineup = auto_lineup(pool + floor, slots)
        week_total = lineup.total
        for pid in lineup.players:
            chances = absence.get(pid)
            q = chances[min(index, len(chances) - 1)] if chances else 0.0
            if q <= 1e-9 or pid not in mine:
                continue
            rest = [p for p in pool if p.id != pid] + floor
            week_total -= q * (lineup.total - auto_lineup(rest, slots).total)
        total += week_total
    return total
