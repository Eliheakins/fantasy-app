"""
Rosetta Stone: DuckDB views/tables over Parquet shards, silver/gold aggregates, JSON manifests.

Run after `dataPipeline` has written `nfl_pbp_*.parquet`, `cfb_pbp_*.parquet`.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from rosetta_ids import load_deduped_player_hub

# Matches nfl_pipeline.EXPECTED_RUN_YARDS_ALIAS (NGS `expected_rush_yards` rename).
EXPECTED_RUN_YARDS_ALIAS = "expected_run_yards"

# --- Column manifest text (NLQ / LLM); PBP aligned with nflverse where names match. -----------

_RAW_STITCHED_SHARED: dict[str, str] = {
    "filename": (
        "Absolute path to the source Parquet file; parse `nfl_pbp_YYYY.parquet` / "
        "`cfb_pbp_YYYY.parquet` for season if `season` is missing or suspect."
    ),
    "play_id": "Unique play identifier within the stitched schema (derived from game keys + play number).",
    "old_game_id": "Legacy / string game identifier used to join participation (NFL).",
    "game_id": "Canonical game identifier.",
    "season": "League season year (calendar year as used in nflverse / sportsdataverse).",
    "week": "Week of the season (REG or POST context per `season_type`).",
    "season_type": "REG (regular) or POST (playoffs), NFL-style encoding for both leagues.",
    "posteam": "Offensive team abbreviation on the play.",
    "defteam": "Defensive team abbreviation on the play.",
    "posteam_type": "Whether offense is home or away.",
    "down": "Current down (1–4) on the play.",
    "ydstogo": "Yards needed for a first down.",
    "yardline_100": "Yards from opponent end zone (0–100); red zone typically yardline_100 ≤ 20.",
    "qtr": "Quarter (or period for CFB-mapped data).",
    "game_seconds_remaining": "Seconds remaining in regulation in the game clock.",
    "score_differential": "Offensive team score minus defensive team score.",
    "goal_to_go": "True if offense is in goal-to-go situation.",
    "play_type": "pass or run (scrimmage); other types filtered out upstream.",
    "first_down": "Whether the play gained a first down.",
    "yards_gained": "Net yards gained on the play for the offense.",
    "air_yards": "Air yards on pass attempts (NFL); null for CFB stitch where unavailable.",
    "yards_after_catch": "YAC on completions (NFL); null for CFB stitch where unavailable.",
    "complete_pass": "Completed pass indicator.",
    "incomplete_pass": "Incomplete pass indicator.",
    "interception": "Interception on the play.",
    "fumble_lost": "Fumble lost (NFL); may be null in CFB stitch.",
    "sack": "Sack taken on the play.",
    "qb_hit": "QB hit (NFL); may be null in CFB stitch.",
    "touchdown": "Touchdown scored on the play.",
    "pass_touchdown": "Passing touchdown.",
    "rush_touchdown": "Rushing touchdown.",
    "epa": (
        "Expected Points Added — change in expected points from before to after the play "
        "(offense; nflverse definition for NFL; cfbfastR EPA for CFB-mapped rows)."
    ),
    "qb_epa": "EPA attributed to the QB (NFL); null in CFB stitch.",
    "success": "Binary success (positive EPA threshold) per source model.",
    "cpoe": "Completion probability over expected (NFL); null in CFB stitch.",
    "xpass": "Expected pass indicator (NFL); null in CFB stitch.",
    "xyac_epa": "Expected YAC EPA component (NFL); null in CFB stitch.",
    "passer_player_id": "GSIS-style passer id (NFL) or ESPN id string (CFB).",
    "passer_player_name": "Passer display name.",
    "rusher_player_id": "Rusher id (same id scheme as passer for league).",
    "rusher_player_name": "Rusher display name.",
    "receiver_player_id": "Target receiver id on pass plays.",
    "receiver_player_name": "Receiver display name.",
    "wpa": "Win probability added on the play.",
    "vegas_wpa": "WPA using closing spread (NFL); null in CFB stitch.",
    "temp": "Game temperature (NFL); null in CFB stitch.",
    "wind": "Wind speed (NFL); null in CFB stitch.",
    "offense_personnel": "Offensive personnel string from participation (NFL); empty for CFB.",
    "defenders_in_box": "Defenders in box (NFL participation); 0 for CFB.",
    "number_of_pass_rushers": "Pass rushers (NFL participation); 0 for CFB.",
    "avg_time_to_throw": "NGS weekly: average time to throw (NFL); 0 for CFB.",
    "avg_intended_air_yards": "NGS weekly: average intended air yards (NFL).",
    "passer_rating": "NGS-derived passer rating snapshot (NFL).",
    "avg_separation": "NGS receiving: average separation (NFL).",
    "avg_cushion": "NGS receiving: average cushion (NFL).",
    "avg_expected_yac": "NGS receiving: expected YAC (NFL).",
    "avg_time_to_los": "NGS rushing: time to line of scrimmage (NFL).",
    EXPECTED_RUN_YARDS_ALIAS: "NGS rushing expected rush yards (NFL); 0 for CFB.",
    "efficiency": "NGS rush efficiency metric (NFL); 0 for CFB.",
    "is_red_zone": "True when yardline_100 ≤ 20 (offense inside the 20).",
}

_HUB: dict[str, str] = {
    "bridge_id": "Internal surrogate primary key for joins (stable after deterministic sort).",
    "display_name": "Player display name from DynastyProcess `name`.",
    "nfl_id": "NFL GSIS id when known (DynastyProcess `gsis_id`); null for college-only rows.",
    "cfb_id": "ESPN athlete id as string (DynastyProcess `espn_id`); joins CFB PBP player ids.",
    "position": "Listed position.",
    "college": "College / school string from DynastyProcess.",
}

_SILVER: dict[str, str] = {
    "player_id": "Participant id for the aggregation (passer/receiver on pass, rusher on run).",
    "season": "Season year aggregated.",
    "epa_per_play": "Mean EPA over plays attributed to this player_id in that season.",
    "total_yards": "Sum of yards_gained on attributed plays.",
    "play_count": "Count of attributed participant rows (one per role per play).",
}

_GOLD: dict[str, str] = {
    "bridge_id": "player_hub bridge id; null if silver player_id had no hub match (LEFT JOIN).",
    "display_name": "From player_hub when matched; otherwise null.",
    "nfl_id": "GSIS id: from hub when matched, else coalesced from NFL silver player_id for filter parity.",
    "cfb_id": "ESPN id string: from hub when matched, else coalesced from CFB silver player_id.",
    "season": "Season year.",
    "level": "NFL or CFB segment label.",
    "epa_per_play": "From silver_*_stats.",
    "total_yards": "From silver_*_stats.",
    "play_count": "From silver_*_stats.",
}


def _sql_path(p: Path) -> str:
    return p.resolve().as_posix().replace("'", "''")


def _describe_columns(con: duckdb.DuckDBPyConnection, relation: str) -> list[str]:
    rows = con.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()
    return [r[0] for r in rows]


def _manifest_columns(table: str, column_names: list[str], lookup: dict[str, str]) -> dict[str, str]:
    generic_pbp = (
        "Stitched PBP column; see https://nflreadr.nflverse.com/articles/dictionary_pbp.html "
        "for NFL semantics (CFB rows use the same column names where mapped)."
    )
    out: dict[str, str] = {}
    for name in column_names:
        if name in lookup:
            out[name] = lookup[name]
        elif table in ("raw_nfl_pbp", "raw_cfb_pbp"):
            out[name] = generic_pbp
        else:
            out[name] = f"Column `{name}` on `{table}`."
    return out


def _write_table_manifest(manifest_dir: Path, table: str, columns: dict[str, str]) -> None:
    manifest_dir.mkdir(parents=True, exist_ok=True)
    path = manifest_dir / f"{table}.json"
    payload = {"table": table, "columns": columns}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_manifests(con: duckdb.DuckDBPyConnection, manifest_dir: Path) -> None:
    manifest_dir = Path(manifest_dir)

    # Pre-build stitched lookup: explicit + any PBP_COLS not yet covered
    stitched_lookup = dict(_RAW_STITCHED_SHARED)

    for league, table in (("NFL", "raw_nfl_pbp"), ("CFB", "raw_cfb_pbp")):
        cols = _describe_columns(con, table)
        desc = _manifest_columns(table, cols, stitched_lookup)
        if league == "CFB":
            for k in list(desc.keys()):
                if k == "epa":
                    desc[k] = (
                        "Expected Points Added from cfbfastR/sportsdataverse, stored under "
                        "the nflverse column name `epa`."
                    )
        _write_table_manifest(manifest_dir, table, desc)

    for table, static in (
        ("player_hub", _HUB),
        ("silver_nfl_stats", _SILVER),
        ("silver_cfb_stats", _SILVER),
        ("gold_unified_performance", _GOLD),
    ):
        cols = _describe_columns(con, table)
        desc = _manifest_columns(table, cols, static)
        _write_table_manifest(manifest_dir, table, desc)

    index = {
        "tables": [
            "player_hub",
            "raw_nfl_pbp",
            "raw_cfb_pbp",
            "silver_nfl_stats",
            "silver_cfb_stats",
            "gold_unified_performance",
        ],
        "files": {t: f"{t}.json" for t in ["player_hub", "raw_nfl_pbp", "raw_cfb_pbp", "silver_nfl_stats", "silver_cfb_stats", "gold_unified_performance"]},
    }
    (manifest_dir / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")


_SILVER_SQL = """
CREATE OR REPLACE TABLE {name} AS
WITH pass_plays AS (
  SELECT * FROM {raw} WHERE play_type = 'pass'
),
run_plays AS (
  SELECT * FROM {raw} WHERE play_type = 'run'
),
long_plays AS (
  SELECT CAST(passer_player_id AS VARCHAR) AS player_id, season, epa, yards_gained, play_id
  FROM pass_plays
  WHERE passer_player_id IS NOT NULL
  UNION ALL
  SELECT CAST(receiver_player_id AS VARCHAR), season, epa, yards_gained, play_id
  FROM pass_plays
  WHERE receiver_player_id IS NOT NULL
  UNION ALL
  SELECT CAST(rusher_player_id AS VARCHAR), season, epa, yards_gained, play_id
  FROM run_plays
  WHERE rusher_player_id IS NOT NULL
)
SELECT
  player_id,
  season,
  AVG(epa) AS epa_per_play,
  SUM(yards_gained) AS total_yards,
  COUNT(*) AS play_count
FROM long_plays
GROUP BY player_id, season
"""


def build_rosetta_layer(data_dir: Path) -> None:
    """
    Build player_hub.parquet, DuckDB silver/gold (in-memory build), materialized gold Parquet,
    and JSON manifests under `<data_dir>/manifests/`.
    """
    data_dir = Path(data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    hub = load_deduped_player_hub()
    hub_path = data_dir / "player_hub.parquet"
    hub.write_parquet(hub_path)
    print(f"✅ player_hub: {hub_path} ({hub.height} rows)")

    base = _sql_path(data_dir)
    hub_sql = _sql_path(hub_path)

    nfl_glob = f"{base}/nfl_pbp_*.parquet"
    cfb_glob = f"{base}/cfb_pbp_*.parquet"

    con = duckdb.connect(database=":memory:")

    con.execute(
        f"""
        CREATE OR REPLACE VIEW raw_nfl_pbp AS
        SELECT * FROM read_parquet('{nfl_glob}', union_by_name=true, filename=true);
        """
    )
    con.execute(
        f"""
        CREATE OR REPLACE VIEW raw_cfb_pbp AS
        SELECT * FROM read_parquet('{cfb_glob}', union_by_name=true, filename=true);
        """
    )

    con.execute(
        f"""
        CREATE OR REPLACE TABLE player_hub AS
        SELECT * FROM read_parquet('{hub_sql}');
        """
    )

    con.execute(_SILVER_SQL.format(name="silver_nfl_stats", raw="raw_nfl_pbp"))
    con.execute(_SILVER_SQL.format(name="silver_cfb_stats", raw="raw_cfb_pbp"))

    con.execute(
        """
        CREATE OR REPLACE VIEW gold_unified_performance AS
        SELECT
          h.bridge_id,
          h.display_name,
          COALESCE(h.nfl_id, CAST(s.player_id AS VARCHAR)) AS nfl_id,
          h.cfb_id AS cfb_id,
          s.season,
          'NFL'::VARCHAR AS level,
          s.epa_per_play,
          s.total_yards,
          s.play_count
        FROM silver_nfl_stats s
        LEFT JOIN player_hub h ON s.player_id = h.nfl_id
        UNION ALL
        SELECT
          h.bridge_id,
          h.display_name,
          h.nfl_id AS nfl_id,
          COALESCE(h.cfb_id, CAST(s.player_id AS VARCHAR)) AS cfb_id,
          s.season,
          'CFB'::VARCHAR AS level,
          s.epa_per_play,
          s.total_yards,
          s.play_count
        FROM silver_cfb_stats s
        LEFT JOIN player_hub h ON s.player_id = h.cfb_id
        """
    )

    gold_path = data_dir / "gold_unified_performance.parquet"
    gp = _sql_path(gold_path)
    con.execute(
        f"""
        COPY (SELECT * FROM gold_unified_performance) TO '{gp}' (FORMAT PARQUET);
        """
    )
    n_gold = con.execute("SELECT COUNT(*) FROM gold_unified_performance").fetchone()[0]
    print(f"✅ gold_unified_performance: {gold_path} ({n_gold} rows materialized)")

    manifest_dir = data_dir / "manifests"
    write_manifests(con, manifest_dir)
    print(f"✅ manifests: {manifest_dir}")

    con.close()


if __name__ == "__main__":
    import os

    _backend_root = Path(__file__).resolve().parent.parent
    _default_data = _backend_root / "data"
    _override = os.environ.get("DATA_LOCAL_DIR", "").strip()
    d = Path(_override).resolve() if _override else _default_data
    build_rosetta_layer(d)
