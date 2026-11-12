"""Streaming candidates and the This week action list."""

import json
import warnings
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from fantasy._engine import _id_map, _league, _names, _read, _week_values
from fantasy._leagues import my_league
from fantasy._lineup import _flag_status, _is_out, lineup, win_probability
from fantasy._market import waivers
from fantasy._schemas import ENGINE_SCHEMAS, empty
from fantasy.config import load_config
from fantasy.sim import moves
from fantasy.sim.availability import kickoffs, missing_kickoffs
from fantasy.sim.lineup import CONSTANT_SLOTS, Player, auto_lineup, lineup_slots
from fantasy.sim.lineup import ELIGIBLE as SLOT_ELIGIBLE
from fantasy.sim.odds import LeagueData
from fantasy.sim.roster import free_agents, ros_value
from fantasy.teams import TEAM_MAP

STREAM_WEEKS = 3


def _kd_owned(kind: str, rostered: pl.DataFrame, data_dir: Path | None) -> pl.DataFrame:
    """Rostered K or DEF rows (every roster column) with their `unit`: the nflverse id for a
    kicker, the team code for a defense."""
    players = _read("sleeper_players", data_dir).select("sleeper_id", "full_name", "position")
    if kind == "DEF":
        owned = rostered.join(players, on="sleeper_id").filter(pl.col("position") == "DEF")
        return owned.with_columns(
            pl.col("sleeper_id")
            .replace_strict(TEAM_MAP, default=pl.col("sleeper_id"))
            .alias("unit")
        )
    id_map = _read("id_map", data_dir, area="derived").select("sleeper_id", "gsis_id")
    owned = rostered.join(id_map, on="sleeper_id").join(players, on="sleeper_id")
    return owned.filter(pl.col("position") == "K").rename({"gsis_id": "unit"})


def _kd_names(kind: str, units: pl.Series, data_dir: Path | None) -> dict[str, str]:
    if kind == "DEF":
        return {u: f"{u} D/ST" for u in units}
    return _names(data_dir)


def streamers(
    league_key: str,
    kind: str,
    top_n: int = 8,
    data_dir: Path | None = None,
    team: int | None = None,
) -> pl.DataFrame:
    """Best free K or DEF over the next weeks, plus mine for comparison. kind is "K" or "DEF"."""
    me = my_league(league_key, data_dir, team)
    if me is None or kind not in ("K", "DEF"):
        return empty("streamers")
    lid, current, mine = me["league_id"], int(me["current_week"]), me["roster_id"]
    proj = (
        _read("streaming_projection", data_dir, area="derived")
        .filter((pl.col("league_id") == lid) & (pl.col("kind") == kind))
        .filter(pl.col("week") < current + STREAM_WEEKS)
    )
    rostered = _read("rosters", data_dir).filter(pl.col("league_id") == lid)
    owned = _kd_owned(kind, rostered, data_dir)
    name = _kd_names(kind, proj["unit"].unique(), data_dir)
    mine_units = set(owned.filter(pl.col("roster_id") == mine)["unit"])
    taken_units = set(owned["unit"]) - mine_units
    totals = proj.group_by("unit", "team").agg(
        pl.col("projection").filter(pl.col("week") == current).sum().alias("this_week"),
        pl.col("projection").sum().alias("next_three"),
    )
    rows = totals.with_columns(
        pl.col("unit").replace_strict(name, default=pl.col("unit")).alias("name"),
        pl.col("unit").is_in(list(mine_units)).alias("is_mine"),
    )
    free = rows.filter(~pl.col("unit").is_in(list(taken_units | mine_units)))
    keep = pl.concat(
        [rows.filter(pl.col("is_mine")), free.sort("next_three", descending=True).head(top_n)]
    )
    return keep.select(*ENGINE_SCHEMAS["streamers"]).sort("next_three", descending=True)


UNAVAILABLE = frozenset({"Out", "Doubtful", "IR", "PUP", "Sus", "NFI"})


LINEUP_GAP = 1.0  # expected points below the best lineup before the gap is worth a note


WAIVER_PLAYOFF_GAIN = 0.005  # playoff odds change that makes an add worth mentioning
WAIVER_TITLE_GAIN = 0.005  # title odds change that does the same once the bracket is seeded


def actions(
    league_key: str,
    n: int = 3,
    odds: pl.DataFrame | None = None,
    adds: pl.DataFrame | None = None,
    data_dir: Path | None = None,
    team: int | None = None,
) -> pl.DataFrame:
    """The most useful things to do now, most urgent first: kind and text.

    Order: injured or out players in your lineup, a lineup change, then a waiver add. `odds` is a
    `win_probability` result to reuse; `adds` a `waivers`-shaped frame (see `stored_adds`) that
    skips the waiver re-simulation.
    """
    loaded = _league(league_key, data_dir, team)
    rows = lineup(league_key, loaded=loaded, data_dir=data_dir, team=team)
    found: list[tuple[str, str]] = []
    if not rows.is_empty():
        found.extend(
            ("Injury", f"{r['full_name']} is {r['injury']} and in your lineup")
            for r in rows.filter(pl.col("starting_now") & ~pl.col("locked")).iter_rows(named=True)
            if r["injury"] in UNAVAILABLE
        )
        known = bool(rows["starting_now"].any())
        gap = float(
            rows.filter(pl.col("recommended"))["projection"].to_numpy().sum()
            - rows.filter(pl.col("starting_now"))["projection"].to_numpy().sum()
        )
        by_name = rows["full_name"]
        if known and gap >= LINEUP_GAP:
            start = by_name.filter(rows["recommended"] & ~rows["starting_now"]).to_list()
            sit = by_name.filter(rows["starting_now"] & ~rows["recommended"]).to_list()
            found.append(
                ("Lineup", f"Start {', '.join(start)} over {', '.join(sit)} (+{gap:.1f} points)")
            )
    if odds is None:
        odds = win_probability(league_key, loaded=loaded, data_dir=data_dir, team=team)
    if not odds.is_empty():
        by_option = {r["option"]: r for r in odds.iter_rows(named=True)}
        pick, best = by_option["win_prob"], by_option["max_points"]
        if pick["tag"] != "same as max points":
            names = dict(zip(rows["gsis_id"], rows["full_name"], strict=True))
            ins = [names[i] for i in set(pick["gsis_ids"]) - set(best["gsis_ids"])]
            out = [names[i] for i in set(best["gsis_ids"]) - set(pick["gsis_ids"])]
            found.append(
                (
                    "Win probability",
                    f"{pick['tag'].capitalize()}: start {', '.join(ins)} over {', '.join(out)} "
                    f"({pick['win_prob']:.1%} vs {best['win_prob']:.1%} to win)",
                )
            )
    if adds is None:
        adds = waivers(league_key, loaded=loaded, data_dir=data_dir, team=team)
    if not adds.is_empty():
        data = loaded[0]
        # from the playoff start the seeds are fixed, so playoff_delta is always 0: use the title
        odds_kind, gain = (
            ("title", WAIVER_TITLE_GAIN)
            if data.current_week >= data.playoff_start
            else ("playoff", WAIVER_PLAYOFF_GAIN)
        )
        col = f"{odds_kind}_delta"
        top = adds.sort(col, descending=True).row(0, named=True)
        if top[col] >= gain:
            found.append(
                (
                    "Waiver",
                    f"Add {top['full_name']}, drop {top['drop_name']}: "
                    f"{top[col]:+.1%} {odds_kind} odds, {top['delta_points']:+.1f} points",
                )
            )
    return pl.DataFrame(found[:n], schema={"kind": pl.String, "text": pl.String}, orient="row")


FILL_INS = 3
BASE_IR_STATUSES = frozenset({"IR", "PUP"})
SKILL = frozenset({"QB", "RB", "WR", "TE"})


@dataclass(frozen=True)
class HoleInputs:
    """Everything `find_holes` reads, as plain values. `value` of a Player is this week's
    projection (0 when he has none); `startable` holds ids with a known kickoff still ahead."""

    slots: tuple[str, ...]
    starters: tuple[Player, ...]
    bench: tuple[Player, ...]
    free: tuple[Player, ...]
    out: frozenset[str]
    bye: frozenset[str]
    startable: frozenset[str]
    ros: dict[str, float]
    names: dict[str, str]


def find_holes(i: HoleInputs) -> list[dict[str, Any]]:
    """Starting slots left with nobody playing (bye, out, empty) that no bench player covers,
    each with the best free agents for it. A bench player covers one hole at most."""
    skill_slots = [s for s in i.slots if s not in CONSTANT_SLOTS]
    placed = auto_lineup([p for p in i.starters if p.position in SKILL], skill_slots)
    empty = list(skill_slots)
    for slot, _ in placed.slots:
        empty.remove(slot)
    kd_placed: list[tuple[str, str]] = []
    for slot in (s for s in i.slots if s in CONSTANT_SLOTS):
        used = {pid for _, pid in kd_placed}
        unit = next((p for p in i.starters if p.position == slot and p.id not in used), None)
        if unit is None:
            empty.append(slot)
        else:
            kd_placed.append((slot, unit.id))
    found: list[tuple[str, str, str | None]] = []
    for slot, held in [*placed.slots, *kd_placed]:
        why = "bye" if held in i.bye else "out" if held in i.out else None
        if why:
            found.append((why, slot, held))
    found += [("empty", slot, None) for slot in empty]
    cover = sorted(
        (p for p in i.bench if p.id in i.startable and p.id not in i.out and p.id not in i.bye),
        key=lambda p: (-p.value, p.id),
    )
    drop = min(i.bench, key=lambda p: (i.ros.get(p.id, 0.0), p.id), default=None)
    drop_name = i.names.get(drop.id, drop.id) if drop else None
    rows: list[dict[str, Any]] = []
    for kind, slot, pid in found:
        fits = SLOT_ELIGIBLE.get(slot, frozenset({slot}))
        taken = next((p for p in cover if p.position in fits), None)
        if taken is not None:
            cover.remove(taken)
            continue
        fills = sorted(
            (p for p in i.free if p.position in fits and p.id in i.startable and p.id not in i.out),
            key=lambda p: (-p.value, p.id),
        )[:FILL_INS]
        rows.append(
            {
                "kind": kind,
                "slot": slot,
                "player_name": i.names.get(pid, pid) if pid else None,
                "fill_ins": [
                    {
                        "gsis_id": p.id,
                        "full_name": i.names.get(p.id, p.id),
                        "position": p.position,
                        "projection": p.value,
                        "drop_name": drop_name,
                    }
                    for p in fills
                ],
            }
        )
    return rows


def reserve_rules(settings_json: str | None) -> tuple[int, frozenset[str]]:
    """IR slots a league has and the injury statuses that may use them. Missing or unreadable
    settings mean no slots."""
    try:
        settings = json.loads(settings_json) if settings_json else {}
    except json.JSONDecodeError:
        settings = {}
    if not isinstance(settings, dict):
        settings = {}
    slots = settings.get("reserve_slots")
    allowed = {
        k.removeprefix("reserve_allow_").capitalize()
        for k, v in settings.items()
        if k.startswith("reserve_allow_") and v == 1
    }
    return (slots if isinstance(slots, int) else 0), BASE_IR_STATUSES | allowed


def ir_moves(
    bench_status: dict[str, str], open_slots: int, allowed: frozenset[str], names: dict[str, str]
) -> list[dict[str, Any]]:
    """Bench players who may go to IR, as many as there are open IR slots (by id order)."""
    eligible = sorted(i for i, s in bench_status.items() if s in allowed)[: max(open_slots, 0)]
    return [
        {"kind": "ir_move", "slot": "IR", "player_name": names.get(i, i), "fill_ins": []}
        for i in eligible
    ]


def _week_games(week: int, data_dir: Path | None) -> tuple[dict[str, datetime], set[str]]:
    """Kickoff by NFL team, and every team that has a game this week (kickoff known or not)."""
    schedules = _read("nfl_schedules", data_dir)
    season = load_config().season
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # missing kickoffs are handled by the caller
        kicks = kickoffs(schedules, season, week)
    return kicks, set(kicks) | missing_kickoffs(schedules, season, week)


@dataclass(frozen=True)
class _KdSide:
    starters: tuple[Player, ...] = ()
    bench: tuple[Player, ...] = ()
    free: tuple[Player, ...] = ()
    bye: frozenset[str] = frozenset()
    startable: frozenset[str] = frozenset()
    names: dict[str, str] = field(default_factory=dict)


def _kd_side(
    kind: str,
    data: LeagueData,
    mine: int,
    games: tuple[dict[str, datetime], set[str], dict[str, str], datetime],
    data_dir: Path | None,
) -> _KdSide:
    """My K or DEF units, the free ones with this week's projection, and which have a game."""
    kicks, playing, team_of, now = games
    proj = _read("streaming_projection", data_dir, area="derived").filter(
        (pl.col("league_id") == data.league_id) & (pl.col("kind") == kind)
    )
    team_by_unit = dict(zip(proj["unit"], proj["team"], strict=True))
    this_week = dict(
        proj.filter(pl.col("week") == data.current_week)
        .group_by("unit")
        .agg(pl.col("projection").sum())
        .iter_rows()
    )
    rostered = _read("rosters", data_dir).filter(pl.col("league_id") == data.league_id)
    owned = _kd_owned(kind, rostered, data_dir)

    def team_code(u: str) -> str | None:
        return team_by_unit.get(u) or team_of.get(u) or (u if kind == "DEF" else None)

    def mine_where(starter: bool) -> tuple[Player, ...]:
        rows = owned.filter(
            (pl.col("roster_id") == mine) & ~pl.col("is_ir") & (pl.col("is_starter") == starter)
        )
        return tuple(Player(u, kind, float(this_week.get(u, 0.0))) for u in rows["unit"])

    taken = set(owned["unit"])
    free = tuple(Player(u, kind, float(v)) for u, v in this_week.items() if u not in taken)
    units = {p.id for p in (*mine_where(True), *mine_where(False), *free)}
    teams = {u: team_code(u) for u in units}
    return _KdSide(
        starters=mine_where(True),
        bench=mine_where(False),
        free=free,
        bye=frozenset(u for u, t in teams.items() if playing and t and t not in playing),
        startable=frozenset(u for u, t in teams.items() if t in kicks and kicks[t] > now),
        names=_kd_names(kind, proj["unit"].unique(), data_dir),
    )


def holes(
    league_key: str,
    data_dir: Path | None = None,
    team: int | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """This week's lineup holes and IR moves for my team (see `find_holes`, `ir_moves`)."""
    data, mine = _league(league_key, data_dir, team)
    week, now = data.current_week, now or datetime.now(UTC)
    positions = moves.position_of(data)
    values = _week_values(data, week, positions)
    names = _names(data_dir)
    ids = _id_map(data_dir, "nfl_team").filter(pl.col("gsis_id").is_not_null())
    mine_rows = (
        _read("rosters", data_dir)
        .filter((pl.col("league_id") == data.league_id) & (pl.col("roster_id") == mine))
        .join(ids, on="sleeper_id")
    )
    kicks, playing = _week_games(week, data_dir)
    team_of = dict(zip(ids["gsis_id"], ids["nfl_team"], strict=True))
    bye = frozenset(g for g, t in team_of.items() if playing and t is not None and t not in playing)
    startable = frozenset(g for g, t in team_of.items() if t in kicks and kicks[t] > now)

    def player(g: str) -> Player:
        return Player(g, positions[g], values.get(g, 0.0))

    def usable(g: str) -> bool:
        return g in positions and positions[g] in SKILL

    def role(starter: bool, ir: bool) -> list[str]:
        r = mine_rows.filter(pl.col("is_starter") == starter, pl.col("is_ir") == ir)
        return [g for g in r["gsis_id"] if usable(g)]

    starters, bench, on_ir = role(True, False), role(False, False), role(False, True)
    free = [g for g in free_agents(data) if g in values]
    unavailable = frozenset(
        g
        for g in (*starters, *bench, *free)
        if _flag_status(data, g) in UNAVAILABLE or _is_out(data, g)
    )
    sides = [
        _kd_side(k, data, mine, (kicks, playing, team_of, now), data_dir)
        for k in sorted(CONSTANT_SLOTS)
        if k in data.roster_positions
    ]
    kd_ids = [p.id for side in sides for p in side.bench]
    kd_out = frozenset(
        p.id
        for side in sides
        for p in (*side.starters, *side.bench, *side.free)
        if p.position == "K" and (_flag_status(data, p.id) in UNAVAILABLE or _is_out(data, p.id))
    )
    inputs = HoleInputs(
        slots=(
            *lineup_slots(data.roster_positions),
            *(s for s in data.roster_positions if s in CONSTANT_SLOTS),
        ),
        starters=(*(player(g) for g in starters), *(p for x in sides for p in x.starters)),
        bench=(*(player(g) for g in bench if g in values), *(p for x in sides for p in x.bench)),
        free=(*(player(g) for g in free), *(p for x in sides for p in x.free)),
        out=unavailable | kd_out,
        bye=bye.union(*(x.bye for x in sides)),
        startable=startable.union(*(x.startable for x in sides)),
        ros=ros_value(data, [*bench, *kd_ids]),
        names=names | {k: v for x in sides for k, v in x.names.items()},
    )
    raw = _read("leagues", data_dir).filter(pl.col("league_id") == data.league_id)
    settings = raw["settings"].first() if "settings" in raw.columns and raw.height else None
    reserve, allowed = reserve_rules(settings if isinstance(settings, str) else None)
    status = {g: _flag_status(data, g) for g in bench}
    return [*find_holes(inputs), *ir_moves(status, reserve - len(on_ir), allowed, names)]
