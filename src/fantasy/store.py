"""Parquet store: atomic writes, schema checks, in-memory DuckDB views.

Parquet files under data/ are the source of truth. Each table has one file at
data/<area>/<name>.parquet, where area is raw, derived or archive. Stages register their
tables in SCHEMAS; reads and writes assert the columns and dtypes match.
"""

import os
import re
from pathlib import Path

import duckdb
import polars as pl

from fantasy.config import ROOT

DATA_DIR = ROOT / "data"
AREAS = ("raw", "derived", "archive")
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

_S, _I, _F, _B = pl.String, pl.Int64, pl.Float64, pl.Boolean


def _cols(
    strings: str = "", ints: str = "", floats: str = ""
) -> dict[str, pl.DataType | type[pl.DataType]]:
    """Build a schema from space-separated column names."""
    return {
        **dict.fromkeys(strings.split(), _S),
        **dict.fromkeys(ints.split(), _I),
        **dict.fromkeys(floats.split(), _F),
    }


# table name -> {column: dtype}. Stages add their tables here as they are built.
SCHEMAS: dict[str, dict[str, pl.DataType | type[pl.DataType]]] = {
    # written by sync_sleeper (area: raw)
    "sleeper_players": {
        "sleeper_id": _S,
        "full_name": _S,
        "position": _S,
        "team": _S,
        "status": _S,
        "injury_status": _S,
        "age": _I,
        "years_exp": _I,
        "gsis_id": _S,
        "fantasy_positions": pl.List(_S),
    },
    "leagues": {
        "league_key": _S,
        "league_id": _S,
        "name": _S,
        "season": _I,
        "status": _S,
        "num_teams": _I,
        "current_week": _I,
        "playoff_week_start": _I,
        "playoff_teams": _I,
        "playoff_seed_type": _I,
        "trade_deadline": _I,
        "waiver_type": _I,
        "roster_positions": pl.List(_S),
        "scoring_settings": _S,  # JSON
        "settings": _S,  # JSON
    },
    "league_teams": {
        "league_id": _S,
        "roster_id": _I,
        "owner_id": _S,
        "team_name": _S,
        "is_me": _B,
        "wins": _I,
        "losses": _I,
        "ties": _I,
        "points_for": _F,
        "points_against": _F,
    },
    "rosters": {
        "league_id": _S,
        "roster_id": _I,
        "sleeper_id": _S,
        "is_starter": _B,
        "is_ir": _B,
    },
    "matchups": {
        "league_id": _S,
        "week": _I,
        "roster_id": _I,
        "matchup_id": _I,
        "points": _F,
    },
    "matchup_players": {
        "league_id": _S,
        "week": _I,
        "roster_id": _I,
        "sleeper_id": _S,
        "points": _F,
        "is_starter": _B,
    },
    "transactions": {
        "league_id": _S,
        "week": _I,
        "transaction_id": _S,
        "type": _S,
        "status": _S,
        "created": _I,
        "roster_id": _I,
        "sleeper_id": _S,
        "action": _S,
        "waiver_bid": _I,
    },
    "trending": {"fetched_at": _S, "kind": _S, "sleeper_id": _S, "count": _I},
    # written by crosswalk (area: derived)
    "id_map": {"sleeper_id": _S, "gsis_id": _S, "nfl_team": _S, "match_method": _S},
    # written by score (area: derived)
    "team_games": _cols(
        strings="game_id game_type gameday team opponent roof",
        ints="season week points_for points_against",
        floats="spread total_line team_implied opp_implied temp wind rest",
    )
    | {"is_home": _B},
    "player_points": _cols(
        strings="league_id gsis_id season_type position team opponent_team roof",
        ints="season week",
        floats="points team_implied opp_implied total_line temp wind",
    )
    | {"is_home": _B},
    # written by streaming (area: derived)
    "defense_points": _cols(
        strings="league_id team roof",
        ints="season week",
        floats="points team_implied opp_implied",
    ),
    "streaming_projection": _cols(
        strings="league_id kind unit team", ints="week", floats="projection"
    ),
    # written by simulate (area: derived; the history copy is in archive and only ever appended)
    "sim_season": _cols(
        strings="league_id team_name",
        ints="roster_id as_of_week n_sims",
        floats="p_playoffs p_bye p_title exp_wins",
    ),
    # written by sleeper_projections (area: archive, only ever appended)
    "sleeper_proj_snapshots": _cols(strings="fetched_at sleeper_id stats", ints="week"),
    # written by sleeper_projections (area: derived): Sleeper's projections under each league
    "proj_sleeper": _cols(strings="league_id sleeper_id", ints="week", floats="projection"),
    # written by injuries (area: derived): chance of playing the next four games by injury report
    "injury_effects": _cols(strings="status practice body", ints="n", floats="p0 p1 p2 p3 perf"),
    "sim_seeds": _cols(strings="league_id", ints="roster_id seed", floats="p"),
    "sim_season_history": _cols(
        strings="league_id team_name run_at",
        ints="roster_id as_of_week n_sims",
        floats="p_playoffs p_bye p_title exp_wins",
    ),
    # written by backtest (area: derived)
    "backtest_metrics": _cols(
        strings="league_id position forecaster",
        ints="horizon n",
        floats="rmse mae pinball coverage80",
    ),
    # written by distributions (area: derived). ratio = quantile tau of actual / projected points.
    # cv = sqrt(sum of squared residuals / sum of squared projections), the spread scale
    "marginals": _cols(strings="league_id position", ints="n", floats="tau ratio cv"),
    "correlation_pairs": _cols(
        strings="league_id relation role_a role_b", ints="n", floats="rho_spearman rho"
    ),
    # written by project (area: derived)
    "player_form": _cols(
        strings="league_id gsis_id position team",
        ints="season week n_games",
        floats="form ewma_actual",
    ),
    "proj_baseline": _cols(
        strings="league_id gsis_id position team",
        ints="season week as_of_season as_of_week",
        floats="projection context",
    )
    | {"has_history": _B, "is_future": _B},
    # written by ingest_nfl (area: raw). Only the columns later stages use.
    "nfl_player_stats": _cols(
        strings="player_id player_display_name position season_type team opponent_team "
        "fg_made_list fg_missed_list",
        ints="season week",
        floats="completions attempts passing_yards passing_tds passing_interceptions "
        "sacks_suffered sack_fumbles_lost passing_2pt_conversions carries rushing_yards "
        "rushing_tds rushing_fumbles_lost rushing_2pt_conversions receptions targets "
        "receiving_yards receiving_tds receiving_fumbles_lost receiving_2pt_conversions "
        "target_share air_yards_share special_teams_tds fg_made fg_att fg_missed fg_blocked "
        "fg_made_0_19 fg_made_20_29 fg_made_30_39 fg_made_40_49 fg_made_50_59 fg_made_60_ "
        "fg_missed_0_19 fg_missed_20_29 fg_missed_30_39 fg_missed_40_49 fg_missed_50_59 "
        "fg_missed_60_ pat_made pat_att pat_missed fantasy_points fantasy_points_ppr",
    ),
    "nfl_team_stats": _cols(
        strings="team season_type opponent_team",
        ints="season week",
        floats="attempts carries passing_yards rushing_yards passing_tds rushing_tds "
        "passing_interceptions sacks_suffered def_sacks def_interceptions def_tds def_safeties "
        "def_fumbles_forced fumble_recovery_opp special_teams_tds def_fg_blocks "
        "def_pat_blocks def_punt_blocks",
    ),
    "nfl_snaps": _cols(
        strings="game_id pfr_player_id gsis_id player position team opponent",
        ints="season week",
        floats="offense_snaps offense_pct defense_snaps defense_pct st_snaps st_pct",
    ),
    "nfl_injuries": _cols(
        strings="game_type team gsis_id position full_name report_status "
        "report_primary_injury practice_status practice_primary_injury",
        ints="season week",
    ),
    "nfl_schedules": _cols(
        strings="game_id game_type gameday gametime away_team home_team roof",
        ints="season week away_score home_score",
        floats="spread_line total_line temp wind away_rest home_rest",
    ),
    "nfl_ff_opportunity": _cols(
        strings="game_id player_id full_name position posteam",
        ints="season week",
        floats="pass_attempt rec_attempt rush_attempt pass_fantasy_points_exp "
        "rec_fantasy_points_exp rush_fantasy_points_exp total_fantasy_points_exp "
        "total_fantasy_points total_yards_gained_exp total_touchdown_exp pass_attempt_team "
        "rec_attempt_team rush_attempt_team receptions_exp pass_yards_gained_exp "
        "rec_yards_gained_exp rush_yards_gained_exp pass_touchdown_exp rec_touchdown_exp "
        "rush_touchdown_exp pass_two_point_conv_exp rec_two_point_conv_exp "
        "rush_two_point_conv_exp pass_interception_exp",
    ),
}


def table_path(name: str, area: str = "derived", data_dir: Path = DATA_DIR) -> Path:
    if not _NAME.match(name):
        raise ValueError(f"bad table name {name!r}: use lowercase letters, digits, underscores")
    if area not in AREAS:
        raise ValueError(f"bad area {area!r}: expected one of {AREAS}")
    return data_dir / area / f"{name}.parquet"


def check_schema(name: str, df: pl.DataFrame) -> None:
    if name not in SCHEMAS:
        raise ValueError(f"table {name!r} has no registered schema in store.SCHEMAS")
    expected = SCHEMAS[name]
    actual = dict(df.schema)
    if list(actual) != list(expected):
        raise ValueError(f"{name}: columns {list(actual)} != expected {list(expected)}")
    wrong = {c: (actual[c], t) for c, t in expected.items() if actual[c] != t}
    if wrong:
        raise ValueError(f"{name}: wrong dtypes {wrong} (actual, expected)")


def write_table(
    name: str, df: pl.DataFrame, area: str = "derived", data_dir: Path = DATA_DIR
) -> Path:
    check_schema(name, df)
    path = table_path(name, area, data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    try:
        df.write_parquet(tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return path


def read_table(name: str, area: str = "derived", data_dir: Path = DATA_DIR) -> pl.DataFrame:
    path = table_path(name, area, data_dir)
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run the stage that writes {name!r}")
    df = pl.read_parquet(path)
    check_schema(name, df)
    return df


def connect(data_dir: Path = DATA_DIR) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB with one view per parquet file, named after the table."""
    con = duckdb.connect(":memory:")
    seen: dict[str, Path] = {}
    for area in AREAS:
        for path in sorted((data_dir / area).glob("*.parquet")):
            if path.stem in seen:
                raise ValueError(f"table {path.stem!r} is in two areas: {seen[path.stem]}, {path}")
            seen[path.stem] = path
            escaped = str(path).replace("'", "''")
            con.execute(f"CREATE VIEW \"{path.stem}\" AS SELECT * FROM read_parquet('{escaped}')")
    return con
