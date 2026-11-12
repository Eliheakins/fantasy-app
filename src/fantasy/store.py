"""Parquet store: atomic writes, schema checks.

Parquet files under data/ are the source of truth. Each table has one file at
data/<area>/<name>.parquet, where area is raw, derived or archive. Stages register their
tables in SCHEMAS; reads and writes assert the columns and dtypes match.
"""

import json
import logging
import os
import re
from contextlib import ExitStack
from pathlib import Path

import polars as pl

from fantasy.config import ROOT, SKILL_POSITIONS, load_config
from nfl_stat.pipeline.atomic import atomic_path

log = logging.getLogger(__name__)

DATA_DIR = ROOT / "data"
AREAS = ("raw", "derived", "archive")
# raw and derived tables live in a release: data/current -> data/releases/<id> (fantasy/releases).
# Before the first migration they sit directly in data/raw and data/derived, and that still works.
RELEASE_AREAS = ("raw", "derived")
CURRENT = "current"
RELEASE_ENV = "FANTASY_RELEASE_DIR"  # set by the pipeline for its stages: the release being built
RUN_ID_ENV = "FANTASY_RUN_ID"  # one id per `make refresh`, kept across a retry of a failed run
RUNS_DIR = ".runs"  # inside data/archive: which rows of each table the current run appended
SKILL = list(SKILL_POSITIONS)  # positions the projection and simulation layers cover
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
    # written by sync_sleeper: the division of each roster that has one (settings.division)
    "roster_divisions": {"league_id": _S, "roster_id": _I, "division": _I},
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
    # written by sync_sleeper: Sleeper's playoff brackets; rows are provisional (seeds still move)
    # while fetched_week is before the league's playoff_week_start
    "playoff_brackets": _cols(
        strings="league_id bracket t1_from_kind t2_from_kind",
        ints="r m t1 t2 t1_from_m t2_from_m w l p fetched_week",
    ),
    "trending": {"fetched_at": _S, "kind": _S, "sleeper_id": _S, "count": _I},
    # written by news_archive (area: archive, only ever appended): one snapshot a day of the
    # players-file fields that change through the week; fetched_at is the file's fetch time
    "sleeper_player_status": {
        **_cols(
            strings="sleeper_id team position status injury_status injury_body_part injury_notes "
            "injury_start_date practice_participation depth_chart_position",
            ints="depth_chart_order news_updated",
        ),
        **_cols(strings="team_changed_at fetched_at"),
    },
    # written by stages/run_recorded.py around every `make refresh` step (area: derived, appended;
    # never under data/stat, which is served over HTTP): one row per stage run
    "refresh_runs": _cols(strings="stage finished_at status error run_id", floats="duration_s"),
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
    # written by streaming (area: archive, only ever appended): each refresh's K and DEF
    # projections for every week ahead, so a later check scores what was said before kickoff
    "streaming_snapshots": _cols(
        strings="league_id kind unit team fetched_at", ints="week", floats="projection"
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
    # written by market_values (area: archive, only ever appended): every fetch, same columns
    "market_values_history": _cols(
        strings="format sleeper_id name position fetched_at",
        ints="overall_rank position_rank tier",
        floats="value trend_30_day",
    ),
    # written by sleeper_projections (area: archive, only ever appended)
    "sleeper_proj_snapshots": _cols(strings="fetched_at sleeper_id stats", ints="week"),
    # written by outside_projections (area: archive, only ever appended): other sites' stat lines
    # (JSON, Sleeper stat keys) by name, nflverse team code and position
    "outside_proj_snapshots": _cols(
        strings="source fetched_at source_id name team position stats", ints="season week"
    ),
    # written by prop_points (area: derived): the current week's points implied by prop lines, and
    # each outside source's (FFToday) projection scored under the league, for the blend
    "proj_props": _cols(
        strings="league_id gsis_id fetched_at", ints="season week", floats="projection"
    ),
    "proj_outside": _cols(
        strings="league_id gsis_id source fetched_at", ints="season week", floats="projection"
    ),
    # written by sleeper_projections (area: derived): Sleeper's projections under each league
    "proj_sleeper": _cols(strings="league_id sleeper_id", ints="week", floats="projection"),
    # written by injuries (area: derived): chance of playing the next four games by injury report
    "injury_effects": _cols(strings="status practice body", ints="n", floats="p0 p1 p2 p3 perf"),
    # written by availability (area: derived): chance of playing the current week
    "availability": _cols(strings="gsis_id", ints="season week", floats="p_play"),
    # written by outlook (area: derived): return-from-absence ratios and teammate-vacancy slopes
    "outlook_effects": _cols(strings="position kind", ints="n", floats="value"),
    # written by simulate with sim_season: a team's chance to play (p_reach) and win (p_win) a
    # title-path bracket game in each round; teams that never reach a round have no row
    "sim_bracket": _cols(strings="league_id", ints="roster_id round", floats="p_reach p_win"),
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
    # written by simulate with sim_season, display only (nothing reads it back into odds): a team's
    # playoff odds given it wins `wins` of its next `n_games` (up to four) regular-season games,
    # over the n_runs runs where that happened (p_condition of all runs)
    "sim_win_need": _cols(
        strings="league_id",
        ints="as_of_week roster_id n_games wins n_runs",
        floats="p_condition p_playoffs",
    ),
    # written by digest (area: derived): my top waiver adds and trade ideas as of the last refresh.
    # Waivers: give is the player dropped, get the one added. Trades: my_playoff and my_title as
    # playoff_delta and title_delta. delta_points is for waivers only
    "move_ideas": {
        **_cols(strings="league_id kind partner give get created_at", ints="as_of_week rank"),
        "give_ids": pl.List(_S),
        "get_ids": pl.List(_S),
        **_cols(floats="playoff_delta title_delta se_title delta_points"),
    },
    "sim_season_history": _cols(
        strings="league_id team_name run_at",
        ints="roster_id as_of_week n_sims",
        floats="p_playoffs p_bye p_title exp_wins",
    ),
    # written by data_api.record_live_tick (area: derived): my matchup in the current week at each
    # live tick or manual score refresh (current week only; run_at is the dedupe key)
    "live_win_history": _cols(
        strings="league_id run_at",
        ints="week roster_id my_left opp_left",
        floats="win_prob my_points opp_points my_projected opp_projected",
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
    # written by learn: the same columns as proj_baseline, so every consumer reads either one.
    # With stat_line_model on, projection is E[points | active] (stages/stat_line.py)
    "proj_learned": _cols(
        strings="league_id gsis_id position team",
        ints="season week as_of_season as_of_week",
        floats="projection context",
    )
    | {"has_history": _B, "is_future": _B},
    # written by learn when stat_line_model is on: P(stat line | active) per player-game
    "stat_line": _cols(strings="gsis_id", ints="season week", floats="q"),
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


def resolve(data_dir: Path | None) -> Path:
    """`data_dir`, or the project data folder (read now, not bound at import)."""
    return DATA_DIR if data_dir is None else data_dir


def table_path(name: str, area: str = "derived", data_dir: Path | None = None) -> Path:
    if not _NAME.match(name):
        raise ValueError(f"bad table name {name!r}: use lowercase letters, digits, underscores")
    if area not in AREAS:
        raise ValueError(f"bad area {area!r}: expected one of {AREAS}")
    return area_dir(area, data_dir) / f"{name}.parquet"


def area_dir(area: str, data_dir: Path | None = None) -> Path:
    """Where the tables of `area` are: the release being built (inside a pipeline run), else the
    current release, else the plain folder (before the first migration, and for the archive)."""
    root = resolve(data_dir)
    if area in RELEASE_AREAS:
        building = os.environ.get(RELEASE_ENV)
        if building and root == DATA_DIR:
            return Path(building) / area
        if (root / CURRENT).is_symlink():
            return root / CURRENT / area
    return root / area


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
    tables: dict[str, pl.DataFrame], area: str = "derived", data_dir: Path | None = None
) -> None:
    """Write several tables so that a failure leaves none of them replaced: every table is
    checked and written to a temp file first, and the files are moved into place at the end."""
    for name, df in tables.items():
        check_schema(name, df)
    with ExitStack() as stack:  # each temp file is moved into place only when all are written
        for name, df in tables.items():
            path = table_path(name, area, data_dir)
            path.parent.mkdir(parents=True, exist_ok=True)
            df.write_parquet(stack.enter_context(atomic_path(path)))


def write_table(
    name: str, df: pl.DataFrame, area: str = "derived", data_dir: Path | None = None
) -> Path:
    write_tables({name: df}, area, data_dir)
    return table_path(name, area, data_dir)


class ArchiveMissing(RuntimeError):
    """An archive table is missing while its siblings exist (wrong dir, lost file, bad restore)"""


def read_archive(name: str, data_dir: Path | None = None) -> pl.DataFrame:
    """The archive table. A missing file counts as a first run only when the archive folder holds
    no tables at all; otherwise it raises, because starting a fresh one-snapshot table would hide
    the loss of history that cannot be regenerated."""
    path = table_path(name, "archive", data_dir)
    if path.exists():
        return read_table(name, "archive", data_dir)
    siblings = sorted(p.stem for p in path.parent.glob("*.parquet"))
    if siblings:
        raise ArchiveMissing(
            f"archive table {name!r} is missing from {path.parent} but {siblings} exist: a wrong "
            "data dir, a deleted file or a bad restore. Restore it from a backup; to start it "
            "fresh on purpose, write an empty table with store.write_table(..., 'archive')"
        )
    log.warning("archive %s has no tables yet; starting %r as a first run", path.parent, name)
    return pl.DataFrame(schema=SCHEMAS[name])


def _rows_before_this_run(
    name: str, old: pl.DataFrame, run_id: str | None, data_dir: Path | None
) -> pl.DataFrame:
    """`old` without the rows an earlier append of the same run (a retry after exit 75) added.
    A small file per table records the run id and the row count before that run's first append;
    archive tables only ever grow at the end, so the first rows_before rows are earlier runs."""
    ledger = table_path(name, "archive", data_dir).parent / RUNS_DIR / f"{name}.json"
    if run_id is None:  # a stage run alone: plain append, and forget the run so rows are not cut
        ledger.unlink(missing_ok=True)
        return old
    if ledger.exists():
        recorded = json.loads(ledger.read_text())
        if recorded["run_id"] == run_id:
            if recorded["rows_before"] > old.height:
                raise ValueError(
                    f"{name}: the archive has {old.height} rows, fewer than the "
                    f"{recorded['rows_before']} before run {run_id}; it was changed or restored"
                )
            return old.head(recorded["rows_before"])
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with atomic_path(ledger) as tmp:
        tmp.write_text(json.dumps({"run_id": run_id, "rows_before": old.height}))
    return old


def with_archive(name: str, new: pl.DataFrame, data_dir: Path | None = None) -> pl.DataFrame:
    """The archive table with `new` appended. Appending twice under one FANTASY_RUN_ID (a retry
    after a failed run) replaces the run's earlier rows instead of adding to them. Reads only
    (apart from the run's ledger file); the caller writes."""
    old = read_archive(name, data_dir)
    base = _rows_before_this_run(name, old, os.environ.get(RUN_ID_ENV) or None, data_dir)
    return pl.concat([base, new])


def read_table(name: str, area: str = "derived", data_dir: Path | None = None) -> pl.DataFrame:
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
    root = resolve(data_dir)
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
    root = resolve(data_dir)
    name = projection_name(root)
    table = read_table(name, "derived", root)
    if name == "proj_learned":
        table = table.filter(pl.col("is_future") | (pl.col("season") >= LEARNED_FIRST_CLEAN_SEASON))
    return table
