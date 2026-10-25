"""Waivers, trades and roster strength: moves that change my team (see data_api)."""

import polars as pl

from fantasy import store
from fantasy._engine import _id_map, _league, _names, _read
from fantasy._schemas import ENGINE_SCHEMAS
from fantasy.sim import moves
from fantasy.sim.odds import LeagueData

MIN_GAIN = 0.05  # expected points below this are not worth a roster move


def waivers(
    league_key: str, week: int = 0, loaded: tuple[LeagueData, int] | None = None
) -> pl.DataFrame:
    """Best adds for my team by extra points over the rest of the season (a shortcut)."""
    data, mine = loaded or _league(league_key)
    names = _names()
    adds = [w for w in moves.waiver_candidates(data, mine, top_n=15) if w.delta_mu > MIN_GAIN]
    odds = {r["gsis_id"]: r for r in moves.waiver_odds(data, mine, adds).iter_rows(named=True)}
    trending = _trending_adds()
    rows = [
        {
            "gsis_id": w.gsis_id,
            "full_name": names.get(w.gsis_id, w.gsis_id),
            "position": w.position,
            "drop_name": names.get(w.drop_id, w.drop_id),
            "delta_points": w.delta_mu,
            "playoff_delta": odds[w.gsis_id]["playoff_delta"],
            "title_delta": odds[w.gsis_id]["title_delta"],
            "se_title": odds[w.gsis_id]["se_title"],
            "trending_adds": trending.get(w.gsis_id),
        }
        for w in adds
    ]
    return pl.DataFrame(rows, schema=ENGINE_SCHEMAS["waivers"])


def _trending_adds() -> dict[str, int]:
    """How many Sleeper users added each player in the latest trending pull (nflverse ID)."""
    table = _read("trending", store.DATA_DIR).filter(pl.col("kind") == "add")
    if table.is_empty():
        return {}
    latest = table.filter(pl.col("fetched_at") == table["fetched_at"].max())
    joined = latest.join(_id_map(), on="sleeper_id").filter(pl.col("gsis_id").is_not_null())
    return dict(zip(joined["gsis_id"], joined["count"], strict=True))


def player_weeks(league_key: str, gsis_id: str, n: int = 4) -> pl.DataFrame:
    """Projected points for one player in each of the next n weeks (injury-scaled)."""
    data, _ = _league(league_key)
    rows = data.projections.filter(
        (pl.col("gsis_id") == gsis_id) & (pl.col("week") < data.current_week + n)
    )
    return rows.select("week", "projection").sort("week")


def trade_partners(league_key: str) -> pl.DataFrame:
    data, mine = _league(league_key)
    rows = [(r, data.team_names[r]) for r in data.roster_ids if r != mine]
    return pl.DataFrame(rows, schema=["roster_id", "team_name"], orient="row")


def trade_assets(league_key: str, roster_id: int | None = None) -> pl.DataFrame:
    """A roster's skill players with projected points over the rest of the season."""
    data, mine = _league(league_key)
    ids = moves.team_ids(data, mine if roster_id is None else roster_id)
    names, positions, values = _names(), moves.position_of(data), moves.ros_value(data, ids)
    rows = [(i, names.get(i, i), positions[i], values[i]) for i in ids]
    schema = ["gsis_id", "full_name", "position", "ros_points"]
    return pl.DataFrame(rows, schema=schema, orient="row").sort("ros_points", descending=True)


def evaluate_trade(
    league_key: str, partner_roster_id: int, give_ids: list[str], get_ids: list[str]
) -> pl.DataFrame:
    """Playoff and title odds before and after, for me and the partner. May raise ValueError."""
    data, mine = _league(league_key)
    return moves.evaluate_trade(data, mine, partner_roster_id, list(give_ids), list(get_ids))


def trade_roster_changes(
    league_key: str, partner_roster_id: int, give_ids: list[str], get_ids: list[str]
) -> pl.DataFrame:
    """Players dropped or picked up automatically to keep each roster's size."""
    data, mine = _league(league_key)
    after = moves.apply_trade(data, mine, partner_roster_id, list(give_ids), list(get_ids))
    names, positions = _names(), moves.position_of(data)
    rows = []
    sides = ((mine, give_ids, get_ids), (partner_roster_id, get_ids, give_ids))
    for roster_id, sent, received in sides:
        team = data.team_names[roster_id]
        before_ids = set(moves.team_ids(data, roster_id))
        after_ids = set(moves.team_ids(data, roster_id, after))
        for gid in sorted((before_ids | set(received)) - after_ids - set(sent)):
            rows.append((team, "dropped", names.get(gid, gid), positions[gid]))
        for gid in sorted(after_ids - before_ids - set(received)):
            rows.append((team, "picked up", names.get(gid, gid), positions[gid]))
    schema = ["team_name", "action", "full_name", "position"]
    return pl.DataFrame(rows, schema=schema, orient="row")


FOUND_NUMBERS = ("my_playoff", "my_title", "their_playoff", "their_title", "se_title")


def find_trades(league_key: str) -> pl.DataFrame:
    """Trades (1 for 1, 1 for 2, 2 for 1, 2 for 2) that fill both teams' positions of need, best
    need fit first. May raise ValueError after the deadline.

    Columns: partner, give, get (names with position, joined with " + "), give_ids, get_ids,
    kind ("win-win": both teams' odds rise; "need swap": a small cost for a need), my_fills and
    their_fills (positions of need filled, joined with ", "), my_fit and their_fit (need fit in
    points), my_playoff, my_title, their_playoff, their_title (changes in probability) and
    se_title (paired Monte Carlo error of my_title).
    """
    data, mine = _league(league_key)
    found = moves.find_trades(data, mine)
    names, positions = _names(), moves.position_of(data)

    def label(ids: list[str]) -> str:
        return " + ".join(f"{names.get(g, g)} ({positions[g]})" for g in ids)

    rows = [
        {
            "partner": data.team_names[r["partner_id"]],
            "give": label(r["give_ids"]),
            "get": label(r["get_ids"]),
            "give_ids": r["give_ids"],
            "get_ids": r["get_ids"],
            "kind": r["kind"],
            "my_fills": ", ".join(r["my_needs"]),
            "their_fills": ", ".join(r["their_needs"]),
            "my_fit": r["my_fit"],
            "their_fit": r["their_fit"],
            **{k: r[k] for k in FOUND_NUMBERS},
        }
        for r in found.iter_rows(named=True)
    ]
    schema: dict[str, pl.DataType | type[pl.DataType]] = {
        "partner": pl.String,
        "give": pl.String,
        "get": pl.String,
        "give_ids": pl.List(pl.String),
        "get_ids": pl.List(pl.String),
        "kind": pl.String,
        "my_fills": pl.String,
        "their_fills": pl.String,
        "my_fit": pl.Float64,
        "their_fit": pl.Float64,
        **dict.fromkeys(FOUND_NUMBERS, pl.Float64),
    }
    return pl.DataFrame(rows, schema=schema)


def position_strength(league_key: str) -> pl.DataFrame:
    """My value over replacement by position, with the league rank (1 is strongest).

    Columns: position, vor_per_week (points a week above the stand-in free agent at that
    position, from my best lineup), rank, teams."""
    data, mine = _league(league_key)
    table = moves.position_strength(data)
    return (
        table.filter(pl.col("roster_id") == mine)
        .with_columns(pl.lit(len(data.roster_ids)).alias("teams"))
        .select("position", "vor_per_week", "rank", "teams")
        .sort("position")
    )
