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

from fantasy.sim.lineup import Player, auto_lineup

POSITIONS = ("QB", "RB", "WR", "TE")
REPLACEMENT_SKIP = 2  # the best free agents are adds, not stand-ins
REPLACEMENT_DEPTH = 6  # stand-in candidates kept per position and week
STAND_INS_PER_POSITION = 2  # used per position and week, after dropping the roster's own


def absence_probs(p_now: float, n_weeks: int, hazard: float, stay_out: float) -> list[float]:
    """Chance a player is out in each of the next n_weeks: week 0 from his status, then the
    two-state chain used by the season simulation."""
    q = 1.0 - p_now
    out = [q]
    for _ in range(n_weeks - 1):
        q = q * stay_out + (1.0 - q) * hazard
        out.append(q)
    return out


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
