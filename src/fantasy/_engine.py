"""Engine internals behind data_api: shared table reads, joint draws and injury notes.

Every read takes the data directory it should read (`None`: the project data folder, looked up at
call time), and the viewed team is an argument too: nothing here is ambient except the pinned data
version a job runs under. Tables read here are required: a missing one raises FileNotFoundError.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import replace
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from threading import Lock

import numpy as np
import polars as pl

from fantasy import store
from fantasy.config import load_config
from fantasy.sim import moves
from fantasy.sim.availability import LONG_TERM, games_on, kickoffs, locked_teams
from fantasy.sim.calibration import tier_of
from fantasy.sim.lineup import Lineup, Player, auto_lineup, constant_slot_count, lineup_slots
from fantasy.sim.odds import CurrentWeek, LeagueData, kd_slot_mean
from fantasy.sim.sampler import LEVELS, Slate, correlation_matrix, sample_points

PLAY_PROB_FLOOR = 1e-9  # guards the division by a chance of playing
LINEUP_SEED = 11
KD_SEED_OFFSET = 1000  # K and DEF draws are independent of the player draws


def _read(name: str, data_dir: Path | None, area: str = "raw") -> pl.DataFrame:
    """An optional table, or an empty frame with its columns if no stage has written it yet.

    Core tables go through `store.read_table` directly so that a missing one raises."""
    try:
        return store.read_table(name, area, data_dir)
    except FileNotFoundError:
        return pl.DataFrame(schema=store.SCHEMAS[name])


def _league_settings(league_id: str, data_dir: Path | None) -> str | None:
    """A league's raw Sleeper `settings` JSON from the `leagues` table (None when missing)."""
    table = _read("leagues", data_dir).filter(pl.col("league_id") == league_id)
    settings = table["settings"].first() if "settings" in table.columns and table.height else None
    return settings if isinstance(settings, str) else None


def current_week(frame: pl.DataFrame) -> int | None:
    """The highest `current_week` over a leagues frame, or None when it has none."""
    week = frame["current_week"].max()
    return None if week is None else int(week)  # type: ignore[arg-type]


LEAGUE_CACHE_SIZE = 4


LIVE_BUCKET_MINUTES = 2  # how stale the share of a game left may get while games are on


def _clock_bucket(kicks: dict[str, datetime], now: datetime) -> str:
    """Empty unless a game is on; then a value that changes every LIVE_BUCKET_MINUTES. The share
    of each game left is read off the clock when a league is built, so the cache key must move."""
    if not games_on(kicks, now):
        return ""
    return f"@{int(now.timestamp() // (LIVE_BUCKET_MINUTES * 60))}"


FileStamp = tuple[int, int]  # (mtime_ns, size): what data_version already treats as "changed"


@lru_cache(maxsize=8)
def _week_kickoffs(
    root: str, season: int, _leagues_stamp: FileStamp, _schedules_stamp: FileStamp
) -> dict[str, datetime]:
    """This week's kickoffs, parsed once per state of the two tables (the stamps only key the
    cache, so a rewrite of either file is read again on the next call)."""
    leagues = store.read_table("leagues", "raw", Path(root))
    schedules = store.read_table("nfl_schedules", "raw", Path(root))
    week = current_week(leagues)
    return {} if week is None else kickoffs(schedules, season, week)


def _live_bucket(root: Path, stamps: dict[str, FileStamp]) -> str:
    leagues, schedules = stamps.get("leagues.parquet"), stamps.get("nfl_schedules.parquet")
    if leagues is None or schedules is None:
        return ""
    kicks = _week_kickoffs(str(root), load_config().season, leagues, schedules)
    return _clock_bucket(kicks, datetime.now(UTC))


def data_version(data_dir: Path | None = None) -> str:
    """Latest mtime (ns) and total size of the parquet files under raw/ and derived/ of the data
    directory, plus a clock bucket while games are on. Changes whenever a stage rewrites a table
    or the live clock moves on. Every call stats the files (no TTL, so a write is seen at once);
    only the kickoff parsing is cached, keyed on the stats of the files it reads."""
    root = store.resolve(data_dir)
    raw = {p.name: p.stat() for p in store.area_dir("raw", root).glob("*.parquet")}
    derived = [p.stat() for p in store.area_dir("derived", root).glob("*.parquet")]
    stats = [*raw.values(), *derived]
    if not stats:
        return "0-0"
    stamps = {name: (s.st_mtime_ns, s.st_size) for name, s in raw.items()}
    return f"{max(s.st_mtime_ns for s in stats)}-{sum(s.st_size for s in stats)}" + _live_bucket(
        root, stamps
    )


def file_stamp(version: str) -> str:
    """A data version without its clock bucket: what changes only when a table is rewritten. Jobs
    are keyed on it, so a job that outlives one bucket is still the one a client polls."""
    return version.partition("@")[0]


_PINNED_VERSION: ContextVar[str | None] = ContextVar("pinned_version", default=None)
_BUILD_LOCKS: dict[tuple[str, str], Lock] = {}  # one per (league, data dir): bounded by leagues
_BUILD_LOCKS_GUARD = Lock()


@contextmanager
def pinned_version(version: str) -> Iterator[None]:
    """Make `_league` use this data version (the one a job was keyed with) in this context."""
    token = _PINNED_VERSION.set(version)
    try:
        yield
    finally:
        _PINNED_VERSION.reset(token)


def _league(
    league_key: str, data_dir: Path | None, team: int | None = None
) -> tuple[LeagueData, int]:
    """Simulation inputs for one league and "my" roster id (`team` if given, else the Sleeper
    is_me team), built once per data version and directory.

    Shared across threads: treat it as read-only (nothing in the engine mutates it)."""
    root = store.resolve(data_dir)
    version = _PINNED_VERSION.get() or data_version(root)
    data, mine = _league_cached(league_key, version, str(root))
    if team is None:
        if mine is None:  # a league someone else added: the caller has to say whose team to view
            raise ValueError(
                f"no team is marked is_me in league {league_key!r}; set user_id in config.toml "
                "and run `make refresh`, or name a team"
            )
        return data, mine
    if team not in data.roster_ids:
        raise ValueError(f"unknown team {team} in league {league_key!r}")
    return data, team


# used by the API refresh route and tests
def _clear_league_cache() -> None:
    _build_league.cache_clear()


def _league_cached(league_key: str, version: str, data_dir: str) -> tuple[LeagueData, int | None]:
    """Single-flight: concurrent misses for one league wait for one build."""
    with _BUILD_LOCKS_GUARD:
        lock = _BUILD_LOCKS.setdefault((league_key, data_dir), Lock())
    with lock:
        return _build_league(league_key, version, data_dir)


@lru_cache(maxsize=LEAGUE_CACHE_SIZE)
def _build_league(league_key: str, version: str, data_dir: str) -> tuple[LeagueData, int | None]:
    """Build the league from `data_dir` and the Sleeper is_me roster id (None when no team is
    marked, as in a league someone else added); `version` only keys the cache."""
    from fantasy.sim.league_data import load_league_data  # heavy imports, only when asked

    root = Path(data_dir)
    row = store.read_table("leagues", "raw", root).filter(pl.col("league_key") == league_key)
    if row.is_empty():
        raise ValueError(f"unknown league {league_key!r}")
    league = row.row(0, named=True)
    teams = store.read_table("league_teams", "raw", root)
    mine = teams.filter((pl.col("league_id") == league["league_id"]) & pl.col("is_me"))
    data = load_league_data(league, strict=False, data_dir=root)
    return data, (None if mine.is_empty() else int(mine["roster_id"][0]))


def _league_id(league_key: str, data_dir: Path | None) -> str:
    """The Sleeper league id for a league key: one filtered read, no simulation build."""
    ids = store.read_table("leagues", "raw", data_dir).filter(pl.col("league_key") == league_key)
    if ids.is_empty():
        raise ValueError(f"unknown league {league_key!r}")
    return str(ids["league_id"][0])


def _id_map(data_dir: Path | None, *extra: str) -> pl.DataFrame:
    """Sleeper to nflverse ids, plus any other `id_map` columns asked for."""
    return store.read_table("id_map", "derived", data_dir).select("sleeper_id", "gsis_id", *extra)


def _gsis_players(data_dir: Path | None, player_column: str, *id_columns: str) -> pl.DataFrame:
    """Players with an nflverse id: gsis_id, any extra `id_map` columns, and `player_column`."""
    players = store.read_table("sleeper_players", "raw", data_dir).select(
        "sleeper_id", player_column
    )
    return (
        _id_map(data_dir, *id_columns)
        .join(players, on="sleeper_id")
        .filter(pl.col("gsis_id").is_not_null())
    )


def _names(data_dir: Path | None) -> dict[str, str]:
    """nflverse ID -> player name."""
    joined = _gsis_players(data_dir, "full_name")
    return dict(zip(joined["gsis_id"], joined["full_name"], strict=True))


def _set_starters(league_id: str, week: int, roster_id: int, data_dir: Path | None) -> list[str]:
    """nflverse ids of the players a team has set as starters in Sleeper for a week."""
    return (
        store.read_table("matchup_players", "raw", data_dir)
        .filter(
            (pl.col("league_id") == league_id)
            & (pl.col("week") == week)
            & (pl.col("roster_id") == roster_id)
            & pl.col("is_starter")
        )
        .join(_id_map(data_dir), on="sleeper_id")["gsis_id"]
        .to_list()
    )


def _marginals(league_id: str, data_dir: Path | None) -> pl.DataFrame:
    return store.read_table("marginals", "derived", data_dir).filter(
        pl.col("league_id") == league_id
    )


def _pool(
    data: LeagueData, roster_id: int, positions: dict[str, str], values: dict[str, float]
) -> list[Player]:
    """A team's players with a projection this week."""
    return [
        Player(i, positions[i], values[i]) for i in moves.team_ids(data, roster_id) if i in values
    ]


def _week_lineup(
    data: LeagueData,
    roster_id: int,
    week: int,
    positions: dict[str, str] | None = None,
    by_week: dict[int, dict[str, float]] | None = None,
) -> tuple[list[Player], Lineup]:
    """A team's pool for `week` and its auto-lineup (skill slots only; K and DEF are added by the
    caller). `schedule` and the weeks-ahead grid both read it, so their totals agree."""
    pos = positions if positions is not None else moves.position_of(data)
    values = by_week if by_week is not None else moves.week_values(data)
    pool = _pool(data, roster_id, pos, values.get(week, {}))
    return pool, auto_lineup(pool, lineup_slots(data.roster_positions))


def _week_values(data: LeagueData, week: int, positions: dict[str, str]) -> dict[str, float]:
    """Expected points by player for `week`. In the current week a player whose game is over has
    no projection left, so he counts what he scored: without him a lineup would show empty slots."""
    values = moves.week_values(data).get(week, {})
    if week != data.current_week:
        return values
    final = {i: points for i, (points, share) in data.live.items() if share <= 0 and i in positions}
    return {**values, **final}


def _opponent_of(data: LeagueData, mine: int, week: int) -> int | None:
    """The roster id I play in `week`, if any."""
    return next(
        (b if a == mine else a for a, b in data.pairings.get(week, []) if mine in (a, b)), None
    )


def _tier_edges(marginals: pl.DataFrame) -> dict[str, list[float]]:
    """Per position, the upper projection edges of tiers 0 and 1 (tier 2 is everything above)."""
    rows = marginals.filter(pl.col("tier").is_in([0, 1])).select("position", "tier", "proj_max")
    out: dict[str, dict[int, float]] = {}
    for position, tier, upper in rows.unique().iter_rows():
        out.setdefault(position, {})[tier] = upper
    return {p: [t[0], t[1]] for p, t in out.items() if len(t) == 2}


def _tier(edges: dict[str, list[float]], player: Player) -> int:
    """The marginal tier of a player's projection, or the all-tier shape (-1) if unknown."""
    return tier_of(edges[player.position], player.value) if player.position in edges else -1


def _injury_note(data: LeagueData, gsis_id: str) -> str | None:
    """Injury, body part and the chance of playing this game and the next, for a flagged player."""
    flag = data.injuries.get(gsis_id)
    if flag is None or not flag[0]:
        return None
    status, body, _ = flag
    text = status + (f" ({body.lower()})" if body else "")
    long_term = ", out at least 4 games" if status in LONG_TERM else ""
    if "play_prob" not in data.projections.columns:
        return text + long_term
    rows = (
        data.projections.filter(
            (pl.col("gsis_id") == gsis_id) & (pl.col("week") >= data.current_week)
        )
        .sort("week")
        .head(2)
    )
    chances = rows["play_prob"].to_list()
    if not chances or (long_term and not any(chances)):  # IR's return curve has chances
        return text + long_term
    return (
        text
        + f": {chances[0]:.0%} to play this game"
        + (f", {chances[1]:.0%} next game" if len(chances) > 1 else "")
    )


def _status_and_locks(
    week: int, current_week: int, now: datetime | None = None, *, data_dir: Path | None
) -> tuple[dict[str, str], set[str]]:
    """Injury status by nflverse ID, and ids whose game has started (current week only)."""
    joined = _gsis_players(data_dir, "injury_status", "nfl_team")
    status = {g: s for g, s in zip(joined["gsis_id"], joined["injury_status"], strict=True) if s}
    if week != current_week:
        return status, set()
    started = locked_teams(
        store.read_table("nfl_schedules", "raw", data_dir),
        load_config().season,
        week,
        now or datetime.now(UTC),
    )
    locked = set(joined.filter(pl.col("nfl_team").is_in(started))["gsis_id"].to_list())
    return status, locked


def _play_probs(data: LeagueData, week: int) -> dict[str, float]:
    """Each projected player's chance of playing in `week` (1.0 where not recorded)."""
    if "play_prob" not in data.projections.columns:
        return {}
    rows = data.projections.filter(pl.col("week") == week)
    return dict(zip(rows["gsis_id"], rows["play_prob"], strict=True))


def _constant_moments(
    data: LeagueData, state: CurrentWeek | None, roster_id: int, week: int
) -> tuple[float, float]:
    """Mean and variance of the K and DEF slots: points already scored plus the team's projection
    for what is left. `state` is None for a week not yet under way."""
    counts = constant_slot_count(data.roster_positions)
    open_k = counts.get("K", 0) if state is None else state.open_k
    open_def = counts.get("DEF", 0) if state is None else state.open_def
    scored = 0.0 if state is None else state.kd_actual
    mean = (
        scored
        + open_k * kd_slot_mean(data, "K", roster_id, week)
        + open_def * kd_slot_mean(data, "DEF", roster_id, week)
    )
    return mean, open_k * data.k_var + open_def * data.def_var


def _constant_points(
    data: LeagueData, n_sims: int, seed: int, roster_id: int, week: int,
    state: CurrentWeek | None = None,
) -> np.ndarray:  # fmt: skip
    """K and DEF slots as draws around the team's projection."""
    mean, var = _constant_moments(data, state, roster_id, week)
    draws: np.ndarray = mean + np.sqrt(var) * np.random.default_rng(seed).standard_normal(n_sims)
    return draws


def _opponent_lineup(
    data: LeagueData,
    opp: int,
    week: int,
    positions: dict[str, str],
    values: dict[str, float],
    slots: list[str],
    data_dir: Path | None,
) -> list[str]:
    """Skill players the opponent starts: set in Sleeper if known, else their best lineup."""
    known = [i for i in _set_starters(data.league_id, week, opp, data_dir) if i in positions]
    if week == data.current_week and known:
        return known
    return sorted(auto_lineup(_pool(data, opp, positions, values), slots).players)


def _draw_points(
    data: LeagueData,
    ids: list[str],
    positions: dict[str, str],
    values: dict[str, float],
    plays: dict[str, float],
    tier_means: dict[str, float],
    week: int,
    n_sims: int,
    data_dir: Path | None,
) -> np.ndarray:
    """Joint draws for `ids` this week: marginals and correlations measured in this league.
    `values` are expected points, `plays` each player's chance of playing, and `tier_means` his
    full-game points when he plays, which picks the floor-and-ceiling shape his size has."""
    base = store.read_table(store.projection_name(data_dir), "derived", data_dir).filter(
        (pl.col("league_id") == data.league_id) & (pl.col("week") == week) & pl.col("is_future")
    )
    base = base.with_columns(
        role=pl.col("position")
        + pl.col("projection")
        .rank("ordinal", descending=True)
        .over("team", "position")
        .cast(pl.String)
    )
    info = {r["gsis_id"]: (r["team"], r["role"]) for r in base.iter_rows(named=True)}
    teams = tuple(info.get(i, ("", ""))[0] or "" for i in ids)
    roles = tuple(info.get(i, ("", ""))[1] for i in ids)
    slate = Slate(
        tuple(ids),
        tuple(positions[i] for i in ids),
        teams,
        roles,
        tuple(values.get(i, 0.0) for i in ids),
        tuple(plays.get(i, 1.0) for i in ids),
    )

    pairs = store.read_table("correlation_pairs", "derived", data_dir).filter(
        pl.col("league_id") == data.league_id
    )
    rho: dict[str, dict[tuple[str, str], float]] = {"same_team": {}, "opposing": {}}
    for relation, a, b, r in pairs.select("relation", "role_a", "role_b", "rho").iter_rows():
        rho[relation][(a, b)] = rho[relation][(b, a)] = r
    schedule = store.read_table("nfl_schedules", "raw", data_dir).filter(
        (pl.col("season") == load_config().season) & (pl.col("week") == week)
    )
    opponent_of = {
        **dict(zip(schedule["home_team"], schedule["away_team"], strict=True)),
        **dict(zip(schedule["away_team"], schedule["home_team"], strict=True)),
    }
    marginals = _marginals(data.league_id, data_dir)
    ratios = {
        (position if tier < 0 else f"{position}:{tier}"): g.sort("tau")["ratio"].to_numpy()
        for (position, tier), g in marginals.group_by("position", "tier")
    }
    if any(len(r) != len(LEVELS) for r in ratios.values()):
        raise ValueError("marginals do not have one ratio per quantile level; rerun distributions")
    missing = {positions[i] for i in ids} - {k for k in ratios if ":" not in k}
    if missing:  # the sampler falls back to the all-tier shape for a position
        raise ValueError(f"marginals have no shape for {sorted(missing)}; rerun distributions")
    edges = _tier_edges(marginals)
    tiers = tuple(
        tier_of(edges[positions[i]], tier_means.get(i, 0.0)) if positions[i] in edges else -1
        for i in ids
    )
    slate = replace(slate, tiers=tiers)
    corr = correlation_matrix(slate, rho["same_team"], rho["opposing"], opponent_of)
    return sample_points(slate, corr, ratios, n_sims, LINEUP_SEED)


def _week_points(
    data: LeagueData,
    ids: list[str],
    positions: dict[str, str],
    values: dict[str, float],
    week: int,
    n_sims: int,
    data_dir: Path | None,
) -> tuple[np.ndarray, dict[str, int]]:
    """Joint points draws for `ids` in `week` (live points added in the current week), and each
    id's column in the draws."""
    live = data.live if week == data.current_week else {}
    share = np.array([live.get(i, (0.0, 1.0))[1] for i in ids])
    actual = np.array(
        [live.get(i, (0.0, 1.0))[0] if share[k] < 1.0 else 0.0 for k, i in enumerate(ids)]
    )
    chance = _play_probs(data, week)
    plays = {i: (1.0 if share[k] < 1.0 else chance.get(i, 1.0)) for k, i in enumerate(ids)}
    tier_means = {i: values.get(i, 0.0) / max(chance.get(i, 1.0), PLAY_PROB_FLOOR) for i in ids}
    # a player whose game has started is playing, so what is left is his full-game points
    scaled = {
        i: (tier_means[i] if share[k] < 1.0 else values.get(i, 0.0)) * share[k]
        for k, i in enumerate(ids)
    }
    drawn = _draw_points(data, ids, positions, scaled, plays, tier_means, week, n_sims, data_dir)
    return drawn + actual, {i: j for j, i in enumerate(ids)}


def _slots_of(
    chosen: frozenset[str], mean_of: dict[str, float], positions: dict[str, str], slots: list[str]
) -> list[str]:
    """The slot each chosen player fills (in sorted id order) when the lineup is set best."""
    lineup = auto_lineup([Player(i, positions[i], mean_of[i]) for i in chosen], slots)
    slot_by_id = {pid: slot for slot, pid in lineup.slots}
    return [slot_by_id[i] for i in sorted(chosen)]
