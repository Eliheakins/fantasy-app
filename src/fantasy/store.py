"""Parquet store: atomic writes, schema checks.

Parquet files under data/ are the source of truth. Each table has one file at
data/<area>/<name>.parquet, where area is raw, derived or archive. Stages register their
tables in SCHEMAS; reads and writes assert the columns and dtypes match.
"""

import os
import re
from pathlib import Path

import polars as pl

from fantasy.config import ROOT, load_config

DATA_DIR = ROOT / "data"
AREAS = ("raw", "derived", "archive")
SKILL = ["QB", "RB", "WR", "TE"]  # positions the projection and simulation layers cover
WEEK_STRIDE = 25  # weeks per season in the running index; playoffs reach week 22
_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

_S, _I, _F, _B = pl.String, pl.Int64, pl.Float64, pl.Boolean


# Pro-Football-Reference and Next Gen Stats columns kept per player-week (prefixes: pfr, ngsrec,
# ngsrus, ngspas), written by stages/ingest_role.py
ADVANCED_COLUMNS = (
    "pfr_rushing_broken_tackles pfr_receiving_broken_tackles "
    "pfr_receiving_drop_pct pfr_receiving_rat "
    "ngsrec_avg_cushion ngsrec_avg_separation ngsrec_avg_intended_air_yards "
    "ngsrec_percent_share_of_intended_air_yards ngsrec_receptions ngsrec_targets "
    "ngsrec_catch_percentage ngsrec_yards ngsrec_rec_touchdowns ngsrec_avg_yac "
    "ngsrec_avg_expected_yac ngsrec_avg_yac_above_expectation "
    "ngsrus_efficiency ngsrus_percent_attempts_gte_eight_defenders ngsrus_avg_time_to_los "
    "ngsrus_rush_attempts ngsrus_rush_yards ngsrus_avg_rush_yards ngsrus_rush_touchdowns "
    "ngsrus_expected_rush_yards ngsrus_rush_yards_over_expected "
    "ngsrus_rush_yards_over_expected_per_att ngsrus_rush_pct_over_expected "
    "ngspas_avg_time_to_throw ngspas_avg_completed_air_yards ngspas_avg_intended_air_yards "
    "ngspas_avg_air_yards_differential ngspas_aggressiveness ngspas_max_completed_air_distance "
    "ngspas_avg_air_yards_to_sticks ngspas_attempts ngspas_pass_yards ngspas_pass_touchdowns "
    "ngspas_interceptions ngspas_passer_rating ngspas_completions ngspas_completion_percentage "
    "ngspas_expected_completion_percentage ngspas_completion_percentage_above_expectation "
    "ngspas_avg_air_distance ngspas_max_air_distance"
)


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
    # written by learn (area: archive, only ever appended): each refresh's projections for the next
    # game, both models, so a later check scores what was actually available before kickoff
    "proj_snapshots": _cols(
        strings="league_id gsis_id fetched_at", ints="season week", floats="learned baseline"
    ),
    # written by market_values (area: raw): FantasyCalc values per league setting (`format`)
    "market_values": _cols(
        strings="format sleeper_id name position fetched_at",
        ints="overall_rank position_rank tier",
        floats="value trend_30_day",
    ),
    # written by sleeper_projections (area: archive, only ever appended)
    "sleeper_proj_snapshots": _cols(strings="fetched_at sleeper_id stats", ints="week"),
    # written by sleeper_projections (area: derived): Sleeper's projections under each league
    "proj_sleeper": _cols(strings="league_id sleeper_id", ints="week", floats="projection"),
    # written by injuries (area: derived): chance of playing the next four games by injury report
    "injury_effects": _cols(strings="status practice body", ints="n", floats="p0 p1 p2 p3 perf"),
    # written by availability (area: derived): chance of playing the current week
    "availability": _cols(strings="gsis_id", ints="season week", floats="p_play"),
    # written by outlook (area: derived): return-from-absence ratios and teammate-vacancy slopes
    "outlook_effects": _cols(strings="position kind", ints="n", floats="value"),
    # written by environment (area: derived): offense efficiency and opposing-corner effects
    "environment_effects": _cols(strings="position kind", ints="n", floats="value t"),
    "sim_seeds": _cols(strings="league_id", ints="roster_id seed", floats="p"),
    # written by simulate with sim_season: a team's expected score (mean plus mean shift) and spread
    # in each remaining regular-season week
    "sim_team_weeks": _cols(
        strings="league_id", ints="roster_id week as_of_week", floats="exp_points sd_points"
    ),
    # written by simulate with sim_season: odds for roster_id given winner_id beats loser_id in
    # `week`, over the n_runs runs where that happened (p_condition of all runs)
    "sim_conditional": _cols(
        strings="league_id",
        ints="as_of_week week winner_id loser_id roster_id n_runs",
        floats="p_condition p_playoffs p_title",
    ),
    "sim_season_history": _cols(
        strings="league_id team_name run_at",
        ints="roster_id as_of_week n_sims",
        floats="p_playoffs p_bye p_title exp_wins",
    ),
    # written by backtest (area: derived)
    "backtest_metrics": _cols(
        strings="league_id position forecaster",
        ints="horizon n tier",
        floats="rmse mae pinball coverage80",
    ),
    # written by distributions (area: derived). ratio = quantile tau of actual / projected points.
    # cv = sqrt(sum of squared residuals / sum of squared projections), the spread scale
    "marginals": _cols(strings="league_id position", ints="n tier", floats="tau ratio cv proj_max"),
    "projection_calibration": _cols(strings="league_id position", ints="n", floats="center factor"),
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
    # written by learn: the same columns as proj_baseline, so every consumer reads either one
    "proj_learned": _cols(
        strings="league_id gsis_id position team",
        ints="season week as_of_season as_of_week",
        floats="projection context",
    )
    | {"has_history": _B, "is_future": _B},
    # written by ingest_role (area: raw). Role and context data keyed by player and week.
    "nfl_rosters_weekly": _cols(
        strings="gsis_id", ints="season week", floats="age years_exp draft_pick"
    ),
    "nfl_depth": _cols(strings="gsis_id", ints="season week", floats="depth_rank"),
    "nfl_advanced": _cols(strings="gsis_id", ints="season week", floats=ADVANCED_COLUMNS),
    "nfl_team_pace": _cols(
        strings="team", ints="season week", floats="plays dropbacks pass_oe team_epa"
    ),
    "nfl_ecr": _cols(
        strings="gsis_id",
        ints="season week",
        floats="ecr_pos ecr_pos_sd ecr_pos_range ecr_all ecr_all_sd ecr_all_range",
    ),
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
    "nfl_team_efficiency": _cols(
        strings="team opponent", ints="season week", floats="pass_epa sack_rate"
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


def week_index() -> pl.Expr:
    """A running week count: shifting it back by k weeks crosses season boundaries correctly."""
    return pl.col("season") * WEEK_STRIDE + pl.col("week")


def team_game_index(team_games: pl.DataFrame) -> pl.DataFrame:
    """Each team's regular-season games as (team, season, week, g), g counting from 0 within the
    team's season."""
    return (
        team_games.filter(pl.col("game_type") == "REG")
        .select("team", "season", "week")
        .sort("team", "season", "week")
        .with_columns(pl.int_range(pl.len()).over("team", "season").alias("g"))
    )


def write_tables(
    tables: dict[str, pl.DataFrame], area: str = "derived", data_dir: Path = DATA_DIR
) -> None:
    """Write several tables so that a failure leaves none of them replaced: every table is
    checked and written to a temp file first, and the files are moved into place at the end."""
    for name, df in tables.items():
        check_schema(name, df)
    staged: dict[Path, Path] = {}
    try:
        for name, df in tables.items():
            path = table_path(name, area, data_dir)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".parquet.tmp")
            staged[tmp] = path
            df.write_parquet(tmp)
        for tmp, path in staged.items():
            os.replace(tmp, path)
    finally:
        for tmp in staged:
            tmp.unlink(missing_ok=True)


def write_table(
    name: str, df: pl.DataFrame, area: str = "derived", data_dir: Path = DATA_DIR
) -> Path:
    write_tables({name: df}, area, data_dir)
    return table_path(name, area, data_dir)


def with_archive(name: str, new: pl.DataFrame, data_dir: Path = DATA_DIR) -> pl.DataFrame:
    """The archive table with `new` appended, or `new` alone when no archive exists yet.
    Reads only; the caller writes."""
    try:
        old = read_table(name, "archive", data_dir)
    except FileNotFoundError:
        return new
    return pl.concat([old, new])


def read_table(name: str, area: str = "derived", data_dir: Path = DATA_DIR) -> pl.DataFrame:
    path = table_path(name, area, data_dir)
    if not path.exists():
        raise FileNotFoundError(f"{path} does not exist; run the stage that writes {name!r}")
    df = pl.read_parquet(path)
    check_schema(name, df)
    return df


# proj_learned seasons scored by models trained on later seasons (see stages/learn.py): fine for
# the held-out checks that start in 2024, but not for fits of residual sizes or effects
LEARNED_FIRST_CLEAN_SEASON = 2021


def projection_name(data_dir: Path | None = None) -> str:
    """proj_learned when config.toml says so and the table exists, else proj_baseline."""
    root = DATA_DIR if data_dir is None else data_dir
    if (
        load_config().projection_model == "learned"
        and table_path("proj_learned", "derived", root).exists()
    ):
        return "proj_learned"
    return "proj_baseline"


def projection_table(data_dir: Path | None = None) -> pl.DataFrame:
    """The projections the simulation and its fits use. The learned table leaves out past games
    from the seasons before LEARNED_FIRST_CLEAN_SEASON, which its walk-forward could not score
    cleanly; future rows are kept."""
    root = DATA_DIR if data_dir is None else data_dir
    name = projection_name(root)
    table = read_table(name, "derived", root)
    if name == "proj_learned":
        table = table.filter(pl.col("is_future") | (pl.col("season") >= LEARNED_FIRST_CLEAN_SEASON))
    return table
