"""The only module the dashboard imports: pure reads over the parquet store, no Streamlit.

Tables that no stage has written yet come back empty with the right columns, never as errors.
Engine outputs that do not exist yet (lineup, waivers, odds, trades) return empty frames.
"""

import json
from pathlib import Path

import polars as pl

from fantasy import store
from fantasy.sim import moves
from fantasy.sim.odds import LeagueData

POSITION_ORDER = {"QB": 0, "RB": 1, "WR": 2, "TE": 3, "K": 4, "DEF": 5}
ROSTER_COLUMNS = [
    "sleeper_id",
    "full_name",
    "position",
    "team",
    "injury_status",
    "is_starter",
    "is_ir",
]

_S, _F, _B = pl.String, pl.Float64, pl.Boolean
# Shapes of engine outputs, filled in by later stories (E4, E5).
_ENGINE_STUBS: dict[str, dict[str, pl.DataType | type[pl.DataType]]] = {
    "lineup": {"slot": _S, "sleeper_id": _S, "full_name": _S, "p10": _F, "p50": _F, "p90": _F},
    "waivers": {
        "gsis_id": _S,
        "full_name": _S,
        "position": _S,
        "drop_name": _S,
        "delta_points": _F,
    },
    "season_odds": {"roster_id": _S, "team_name": _S, "p_playoffs": _F, "p_title": _F},
    "kdef": {"team": _S, "position": _S, "week": _S, "projection": _F},
}


def _read(name: str, data_dir: Path, area: str = "raw") -> pl.DataFrame:
    try:
        return store.read_table(name, area, data_dir)
    except FileNotFoundError:
        return pl.DataFrame(schema=store.SCHEMAS[name])


def scoring_labels(scoring: dict[str, float], roster_positions: list[str]) -> list[str]:
    labels = [f"{scoring.get('rec', 0):g} PPR", f"{scoring.get('pass_td', 0):g}-pt pass TD"]
    if scoring.get("pass_int"):
        labels.append(f"{scoring['pass_int']:g} per INT")
    if "SUPER_FLEX" in roster_positions:
        labels.append("Superflex")
    return labels


def leagues(data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """One row per league with my team, record and scoring labels."""
    mine = _read("league_teams", data_dir).filter(pl.col("is_me"))
    joined = _read("leagues", data_dir).join(mine, on="league_id", how="left")
    labels = [
        ", ".join(scoring_labels(json.loads(scoring), positions))
        for scoring, positions in zip(
            joined["scoring_settings"], joined["roster_positions"], strict=True
        )
    ]
    return joined.with_columns(pl.Series("scoring_labels", labels, dtype=pl.String)).select(
        "league_key",
        "league_id",
        "name",
        "current_week",
        "num_teams",
        "roster_id",
        "team_name",
        "wins",
        "losses",
        "ties",
        "points_for",
        "scoring_labels",
    )


def roster(league_key: str, data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """My roster in a league: starters first, then by position."""
    schema = {c: store.SCHEMAS["sleeper_players"].get(c, pl.Boolean) for c in ROSTER_COLUMNS}
    row = leagues(data_dir).filter(pl.col("league_key") == league_key)
    if row.is_empty():
        return pl.DataFrame(schema=schema)
    league_id, roster_id = row["league_id"][0], row["roster_id"][0]
    mine = _read("rosters", data_dir).filter(
        (pl.col("league_id") == league_id) & (pl.col("roster_id") == roster_id)
    )
    players = _read("sleeper_players", data_dir).select(
        "sleeper_id", "full_name", "position", "team", "injury_status"
    )
    return (
        mine.join(players, on="sleeper_id", how="left")
        .with_columns(
            pl.col("position")
            .replace_strict(POSITION_ORDER, default=len(POSITION_ORDER))
            .alias("_order")
        )
        .sort(["is_starter", "_order", "full_name"], descending=[True, False, False])
        .select(ROSTER_COLUMNS)
    )


def unmatched(data_dir: Path = store.DATA_DIR) -> pl.DataFrame:
    """Active non-DEF players with no nflverse ID (shown as "no history")."""
    id_map = _read("id_map", data_dir, area="derived").select("sleeper_id", "gsis_id")
    return (
        _read("sleeper_players", data_dir)
        .filter((pl.col("status") == "Active") & pl.col("team").is_not_null())
        .filter(pl.col("position") != "DEF")
        .select("sleeper_id", "full_name", "position", "team")
        .join(id_map, on="sleeper_id", how="left")
        .filter(pl.col("gsis_id").is_null())
        .select("sleeper_id", "full_name", "position", "team")
        .sort("position", "full_name")
    )


def lineup(league_key: str, week: int, objective: str = "win") -> pl.DataFrame:
    return pl.DataFrame(schema=_ENGINE_STUBS["lineup"])


def _names() -> dict[str, str]:
    """nflverse ID -> player name."""
    ids = _read("id_map", store.DATA_DIR, area="derived").select("sleeper_id", "gsis_id")
    players = _read("sleeper_players", store.DATA_DIR).select("sleeper_id", "full_name")
    joined = ids.join(players, on="sleeper_id").filter(pl.col("gsis_id").is_not_null())
    return dict(zip(joined["gsis_id"], joined["full_name"], strict=True))


def _league(league_key: str) -> tuple[LeagueData, int]:
    """Simulation inputs for one league and my roster id."""
    from fantasy.stages.simulate import load_league_data  # heavy imports, only when asked

    row = store.read_table("leagues", "raw").filter(pl.col("league_key") == league_key)
    if row.is_empty():
        raise ValueError(f"unknown league {league_key!r}")
    league = row.row(0, named=True)
    teams = store.read_table("league_teams", "raw")
    mine = teams.filter((pl.col("league_id") == league["league_id"]) & pl.col("is_me"))
    return load_league_data(league), int(mine["roster_id"][0])


def waivers(league_key: str, week: int = 0) -> pl.DataFrame:
    """Best adds for my team by extra points over the rest of the season (a shortcut)."""
    data, mine = _league(league_key)
    names = _names()
    rows = [
        {
            "gsis_id": w.gsis_id,
            "full_name": names.get(w.gsis_id, w.gsis_id),
            "position": w.position,
            "drop_name": names.get(w.drop_id, w.drop_id),
            "delta_points": w.delta_mu,
        }
        for w in moves.waiver_candidates(data, mine, top_n=15)
    ]
    return pl.DataFrame(rows, schema=_ENGINE_STUBS["waivers"])


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
        for gid in sorted(before_ids - after_ids - set(sent)):
            rows.append((team, "dropped", names.get(gid, gid), positions[gid]))
        for gid in sorted(after_ids - before_ids - set(received)):
            rows.append((team, "picked up", names.get(gid, gid), positions[gid]))
    schema = ["team_name", "action", "full_name", "position"]
    return pl.DataFrame(rows, schema=schema, orient="row")


def season_odds(league_key: str) -> pl.DataFrame:
    return pl.DataFrame(schema=_ENGINE_STUBS["season_odds"])


def kdef(league_key: str, week: int) -> pl.DataFrame:
    return pl.DataFrame(schema=_ENGINE_STUBS["kdef"])
