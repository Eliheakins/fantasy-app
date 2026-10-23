"""The only module the dashboard imports: pure reads over the parquet store, no Streamlit.

Tables that no stage has written yet come back empty with the right columns, never as errors.
Engine outputs that do not exist yet (lineup, waivers, odds, trades) return empty frames.
"""

import json
from pathlib import Path

import polars as pl

from fantasy import store

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
    "waivers": {"sleeper_id": _S, "full_name": _S, "delta_win": _F, "delta_title": _F},
    "season_odds": {"roster_id": _S, "team_name": _S, "p_playoffs": _F, "p_title": _F},
    "kdef": {"team": _S, "position": _S, "week": _S, "projection": _F},
    "trade_eval": {"side": _S, "playoff_before": _F, "playoff_after": _F, "title_after": _F},
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


def waivers(league_key: str, week: int) -> pl.DataFrame:
    return pl.DataFrame(schema=_ENGINE_STUBS["waivers"])


def season_odds(league_key: str) -> pl.DataFrame:
    return pl.DataFrame(schema=_ENGINE_STUBS["season_odds"])


def kdef(league_key: str, week: int) -> pl.DataFrame:
    return pl.DataFrame(schema=_ENGINE_STUBS["kdef"])


def evaluate_trade(league_key: str, give_ids: list[str], get_ids: list[str]) -> pl.DataFrame:
    return pl.DataFrame(schema=_ENGINE_STUBS["trade_eval"])
