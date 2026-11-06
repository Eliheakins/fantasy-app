"""Team-defense scoring and K and DEF projections for streaming.

DEF points come from nflverse team stats under each league's scoring: sacks, interceptions,
fumble recoveries, forced fumbles, safeties, blocks, defensive and special-teams TDs, plus the
points-allowed and yards-allowed tiers. Play-by-play adds what team stats lack (team stats'
`def_tds` are interception returns only): fumble-return TDs, sack yards (yards allowed are net of
them), special-teams takeaways (scored at the special-teams rates) and defensive two-point returns.
Points allowed exclude only touchdowns the opponent's defense scored. This matches Sleeper exactly
in 92 of 94 (Colgate) and 88 of 89 (YinzBurgh) rostered DEF team-weeks of 2026 weeks 1 to 8
(`research/def_scoring_check.py`).

Projection = recent form shrunk toward the league average, plus a slope on the game's implied
total (opponent's for DEF, own team's for K, fit on 2018 onward) and a dome adjustment for K.

Run: uv run python -m fantasy.stages.streaming
"""

import json
import re
from datetime import UTC, datetime

import numpy as np
import polars as pl

from fantasy import store
from fantasy.sim.blend import blend
from fantasy.stages import streaming_model as sm
from fantasy.stages.crosswalk import TEAM_MAP
from nfl_stat.pipeline.pbp_source import read_pbp

HALF_LIFE = 4.0  # games
SHRINK_K = 3.0  # pseudo-games of league average
DOMES = ("dome", "closed")
SCORED_FROM = 2018
BACKTEST_FROM = 2024
MIN_CONTEXT_ROWS = 50  # fewer rows than this and the context fit is skipped
KINDS = ("DEF", "K")
PBP_COLUMNS = [
    "season", "week", "season_type", "posteam", "defteam", "special_teams_play", "sack",
    "yards_gained", "touchdown", "fumble", "interception", "td_team", "fumbled_1_team",
    "fumble_recovery_1_team", "forced_fumble_player_1_team", "defensive_two_point_conv",
]  # fmt: skip
DEFENSE_FACTS = (
    "sack_yards", "fumble_return_tds", "st_fumble_recoveries", "st_fumbles_forced", "def_2pt",
)  # fmt: skip


def tier_terms(scoring: dict[str, float], prefix: str) -> list[tuple[int, int, float]]:
    """(low, high, points) for keys like pts_allow_7_13, pts_allow_0 and pts_allow_35p."""
    terms = []
    for key, weight in scoring.items():
        match = re.fullmatch(prefix + r"_(\d+)(?:_(\d+)|(p))?", key)
        if not match or not weight:
            continue
        low = int(match.group(1))
        high = 10**6 if match.group(3) else int(match.group(2) or low)
        terms.append((low, high, float(weight)))
    return terms


# the schedules call the 2018 and 2019 Raiders OAK; the team stats call them LV
SCHEDULE_TEAM_CODES = {"OAK": "LV"}


def tier_expr(column: str, terms: list[tuple[int, int, float]]) -> pl.Expr:
    expr = pl.lit(0.0)
    for low, high, weight in terms:
        expr = (
            pl.when((pl.col(column) >= low) & (pl.col(column) <= high))
            .then(pl.lit(weight))
            .otherwise(expr)
        )
    return expr


def _team_count(
    plays: pl.DataFrame, team: str, fact: str, when: pl.Expr, value: pl.Expr | None = None
) -> pl.DataFrame:
    """Long rows (team, season, week, fact, value) for the matching plays, credited to the
    `team` column; `value` defaults to 1 per play."""
    return plays.filter(when).select(
        pl.col(team).alias("team"),
        "season",
        "week",
        pl.lit(fact).alias("fact"),
        value=pl.lit(1.0) if value is None else value.cast(pl.Float64),
    )


def defense_play_facts(pbp: pl.DataFrame) -> pl.DataFrame:
    """Per regular-season (team, season, week), from play-by-play, the DEF facts nflverse team
    stats lack: the team's own sack yards lost (as an offense), fumble-return touchdowns, its
    special-teams takeaways and forced fumbles, and defensive two-point returns."""
    flags = ("special_teams_play", "touchdown", "fumble", "sack", "interception")
    plays = pbp.filter(pl.col("season_type") == "REG").with_columns(
        pl.col(c).fill_null(0) for c in flags
    )
    special = pl.col("special_teams_play") == 1
    recovered_by = pl.col("fumble_recovery_1_team")
    takeaway = recovered_by.is_not_null() & (pl.col("fumbled_1_team") != recovered_by)
    fumble_return_td = (
        (pl.col("touchdown") == 1)
        & (pl.col("fumble") == 1)
        & (pl.col("interception") == 0)
        & ~special
        & (pl.col("td_team") != pl.col("posteam"))
        & (pl.col("td_team") == recovered_by)
    )
    forced_by = "forced_fumble_player_1_team"
    long = pl.concat(
        [
            _team_count(
                plays,
                "posteam",
                "sack_yards",
                pl.col("sack") == 1,
                pl.col("yards_gained").fill_null(0),
            ),
            _team_count(plays, "td_team", "fumble_return_tds", fumble_return_td),
            _team_count(
                plays, "fumble_recovery_1_team", "st_fumble_recoveries", special & takeaway
            ),
            _team_count(
                plays, forced_by, "st_fumbles_forced", special & pl.col(forced_by).is_not_null()
            ),
            _team_count(plays, "defteam", "def_2pt", pl.col("defensive_two_point_conv") == 1),
        ]
    )
    return (
        long.group_by("team", "season", "week")
        .agg(pl.col("value").filter(pl.col("fact") == f).sum().alias(f) for f in DEFENSE_FACTS)
        .with_columns(pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64))
    )


def load_play_facts(seasons: range) -> pl.DataFrame:
    """`defense_play_facts` for each season's play-by-play (downloaded if stale)."""
    return pl.concat([defense_play_facts(read_pbp(s, PBP_COLUMNS)) for s in seasons])


def defense_points_frame(
    team_stats: pl.DataFrame,
    team_games: pl.DataFrame,
    scoring: dict[str, float],
    league_id: str,
    facts: pl.DataFrame,
) -> pl.DataFrame:
    """One row per team-game with the DEF points a Sleeper defense would score. `facts` is
    `defense_play_facts`; a team-game missing from it counts as all zeros."""
    stats = (
        team_stats.filter(pl.col("season_type") == "REG")
        .join(facts, on=["team", "season", "week"], how="left")
        .with_columns(pl.col(f).fill_null(0.0) for f in DEFENSE_FACTS)
    )
    opponent = stats.select(
        pl.col("team").alias("opponent_team"),
        "season",
        "week",
        # Sleeper's yards allowed are net of the yards the offense lost on sacks
        yards_allowed=pl.col("passing_yards") + pl.col("rushing_yards") + pl.col("sack_yards"),
        opp_def_tds=pl.col("def_tds") + pl.col("fumble_return_tds"),
    )
    games = team_games.select(
        "season", "week", "team", "points_against", "team_implied", "opp_implied", "roof"
    ).with_columns(pl.col("team").replace(SCHEDULE_TEAM_CODES))
    joined = stats.join(games, on=["season", "week", "team"]).join(
        opponent, on=["season", "week", "opponent_team"]
    )
    played = joined.filter(pl.col("points_against").is_not_null())
    # an inner join drops a team-game whose team code differs between the sources; the rest of the
    # gap is games not yet played
    lost = stats.height - joined.height
    if lost:
        print(f"streaming: league {league_id}: {lost} DEF team-games lost to team code mismatches")
    # return and blocked-kick TDs stay in points allowed; only the other defense's TDs come out
    rows = played.with_columns(allowed=pl.col("points_against") - 6 * pl.col("opp_def_tds"))
    st_recoveries, st_forced = pl.col("st_fumble_recoveries"), pl.col("st_fumbles_forced")
    plays = (
        pl.col("def_sacks") * scoring.get("sack", 0.0)
        + pl.col("def_interceptions") * scoring.get("int", 0.0)
        # team stats count special-teams takeaways and forced fumbles with the defense's
        + (pl.col("fumble_recovery_opp") - st_recoveries).clip(0) * scoring.get("fum_rec", 0.0)
        + st_recoveries * scoring.get("def_st_fum_rec", 0.0)
        + (pl.col("def_fumbles_forced") - st_forced).clip(0) * scoring.get("ff", 0.0)
        + st_forced * scoring.get("def_st_ff", 0.0)
        + pl.col("def_safeties") * scoring.get("safe", 0.0)
        + (pl.col("def_fg_blocks") + pl.col("def_pat_blocks") + pl.col("def_punt_blocks"))
        * scoring.get("blk_kick", 0.0)
        + (pl.col("def_tds") + pl.col("fumble_return_tds")) * scoring.get("def_td", 0.0)
        + pl.col("special_teams_tds") * scoring.get("def_st_td", 0.0)
        + pl.col("def_2pt") * scoring.get("def_2pt", 0.0)
    )
    return rows.select(
        pl.lit(league_id).alias("league_id"),
        "team",
        "season",
        "week",
        (
            plays
            + tier_expr("allowed", tier_terms(scoring, "pts_allow"))
            + tier_expr("yards_allowed", tier_terms(scoring, "yds_allow"))
        ).alias("points"),
        "team_implied",
        "opp_implied",
        "roof",
    ).select(*store.SCHEMAS["defense_points"])


def shrunk_form(prior: np.ndarray, league_mean: float) -> float:
    """Exponentially weighted mean of past points (newest last), pulled toward the league mean."""
    if prior.size == 0:
        return league_mean
    weights = 0.5 ** (np.arange(prior.size)[::-1] / HALF_LIFE)
    total = float(weights.sum())
    return (float((weights * prior).sum()) + SHRINK_K * league_mean) / (total + SHRINK_K)


def fit_context(history: pl.DataFrame, implied: str) -> tuple[float, float]:
    """(slope on the implied total, extra points in a dome) by least squares on history."""
    rows = history.filter(pl.col(implied).is_not_null()).select("points", implied, "roof")
    if rows.height < MIN_CONTEXT_ROWS:
        print(f"streaming: WARNING only {rows.height} rows for {implied}; no context adjustment")
        return 0.0, 0.0
    x = rows[implied].to_numpy() - rows[implied].mean()
    dome = rows["roof"].is_in(DOMES).cast(pl.Float64).to_numpy()
    design = np.column_stack([np.ones_like(x), x, dome])
    coef, *_ = np.linalg.lstsq(design, rows["points"].to_numpy(), rcond=None)
    return float(coef[1]), float(coef[2])


def project_units(
    history: pl.DataFrame,
    upcoming: pl.DataFrame,
    unit: str,
    implied: str,
    use_dome: bool,
) -> pl.DataFrame:
    """Projection for each upcoming (unit, week). `history` has unit, season, week, points,
    <implied>, roof. `upcoming` has unit, team, week, <implied>, roof."""
    if history.is_empty():
        raise ValueError(f"no history to project {unit} from")
    league_mean = float(np.mean(history["points"].to_numpy()))
    slope, dome_bonus = fit_context(history, implied)
    implied_values = history[implied].drop_nulls().to_numpy()
    centre = float(np.mean(implied_values)) if implied_values.size else 0.0
    ordered = history.sort(unit, "season", "week")
    form = {
        key: shrunk_form(g["points"].to_numpy(), league_mean)
        for (key,), g in ordered.group_by(unit, maintain_order=True)
    }
    rows = []
    for r in upcoming.iter_rows(named=True):
        base = form.get(r[unit], league_mean)
        value = r[implied]
        adjust = slope * (value - centre) if value is not None else 0.0
        if use_dome and r["roof"] in DOMES:
            adjust += dome_bonus
        rows.append((r[unit], r["team"], r["week"], base + adjust))
    return pl.DataFrame(rows, schema=[unit, "team", "week", "projection"], orient="row")


def backtest(history: pl.DataFrame, unit: str, implied: str, use_dome: bool) -> tuple[float, float]:
    """RMSE of the walk-forward projection and of the league mean, on seasons 2024 onward."""
    test = history.filter(pl.col("season") >= BACKTEST_FROM)
    errs_model, errs_mean = [], []
    for (season, week), games in test.group_by("season", "week"):
        past = history.filter(
            (pl.col("season") < season) | ((pl.col("season") == season) & (pl.col("week") < week))
        )
        if past.is_empty():
            continue
        upcoming = games.select(unit, pl.col(unit).alias("team"), "week", implied, "roof")
        proj = project_units(past, upcoming, unit, implied, use_dome)
        joined = games.join(proj.select(unit, "projection"), on=unit)
        mean = float(np.mean(past["points"].to_numpy()))
        errs_model += list((joined["points"] - joined["projection"]).to_numpy())
        errs_mean += list((joined["points"] - mean).to_numpy())
    if not errs_model:
        raise ValueError(f"no {unit} games from {BACKTEST_FROM} to score")
    return float(np.sqrt(np.mean(np.square(errs_model)))), float(
        np.sqrt(np.mean(np.square(errs_mean)))
    )


def sleeper_by_unit(league_id: str, id_map: pl.DataFrame) -> pl.DataFrame:
    """Sleeper's projections keyed like ours: nflverse team code for DEF, gsis id for K."""
    try:
        theirs = store.read_table("proj_sleeper").filter(pl.col("league_id") == league_id)
    except FileNotFoundError:
        return pl.DataFrame(schema={"unit": pl.String, "week": pl.Int64, "other": pl.Float64})
    teams = theirs.filter(pl.col("sleeper_id").str.contains(r"^[A-Z]{2,3}$")).select(
        pl.col("sleeper_id").replace_strict(TEAM_MAP, default=pl.col("sleeper_id")).alias("unit"),
        "week",
        other=pl.col("projection"),
    )
    kickers = theirs.join(id_map.select("sleeper_id", "gsis_id"), on="sleeper_id").select(
        pl.col("gsis_id").alias("unit"), "week", other=pl.col("projection")
    )
    return pl.concat([teams, kickers])


def _unit_projection(
    hist: pl.DataFrame,
    ahead: pl.DataFrame,
    features: list[str],
    use_dome: bool,
    kind: str,
    league_id: str,
    id_map: pl.DataFrame,
) -> tuple[pl.DataFrame, tuple[float, float]]:
    """One league's projections for DEF or K, blended with Sleeper's and tagged, and the
    walk-forward RMSE (model, league mean) from the same history. `hist` and `ahead` carry the
    model's features; with too little complete history the plain form-plus-implied-total method
    runs instead."""
    ridge = sm.project(hist, ahead, features)
    if ridge is None:
        proj = project_units(hist, ahead, "unit", "implied", use_dome=use_dome)
        rmse = backtest(hist, "unit", "implied", use_dome=use_dome)
    else:
        proj = ridge.select("unit", "team", "week", "projection")
        try:
            rmse = sm.backtest_rmse(hist, features, BACKTEST_FROM)
        except ValueError:  # no scored week has enough complete earlier rows: report the plain one
            rmse = backtest(hist, "unit", "implied", use_dome=use_dome)
    proj = blend(proj, sleeper_by_unit(league_id, id_map), "unit")
    tagged = proj.with_columns(pl.lit(league_id).alias("league_id"), pl.lit(kind).alias("kind"))
    return tagged, rmse


def _with_k_features(rows: pl.DataFrame, teams: pl.DataFrame, usage: pl.DataFrame) -> pl.DataFrame:
    """Kicker rows (unit, team, opponent_team, season, week, roof) with the K model's features."""
    rows = rows.join(usage.rename({"gsis_id": "unit"}), on=["unit", "season", "week"], how="left")
    return sm.add_team_features(rows, teams).with_columns(
        pl.col("roof").is_in(DOMES).cast(pl.Float64).alias("dome")
    )


def run() -> dict[str, tuple[float, float]]:
    games = store.read_table("team_games")
    stats = store.read_table("nfl_team_stats", "raw")
    leagues = store.read_table("leagues", "raw")
    kickers = store.read_table("player_points").filter(pl.col("position") == "K")
    sleeper = store.read_table("sleeper_players", "raw").filter(
        (pl.col("position") == "K") & (pl.col("status") == "Active") & pl.col("team").is_not_null()
    )
    id_map = store.read_table("id_map").select("sleeper_id", "gsis_id", "nfl_team")
    active_k = sleeper.select("sleeper_id").join(id_map, on="sleeper_id").drop_nulls("gsis_id")
    coded = games.with_columns(
        pl.col("team").replace(SCHEDULE_TEAM_CODES), pl.col("opponent").replace(SCHEDULE_TEAM_CODES)
    )
    teams = sm.team_trailing(
        stats,
        store.read_table("nfl_team_efficiency", "raw"),
        store.read_table("nfl_team_pace", "raw"),
        coded,
    )
    player_stats = store.read_table("nfl_player_stats", "raw")
    last_season = int(stats["season"].max())  # type: ignore[arg-type]
    facts = load_play_facts(range(SCORED_FROM, last_season + 1))
    defense_frames, projections, report = [], [], {}
    for lg in leagues.iter_rows(named=True):
        lid, current = lg["league_id"], int(lg["current_week"])
        scoring = json.loads(lg["scoring_settings"])
        points = defense_points_frame(stats, games, scoring, lid, facts).filter(
            pl.col("season") >= SCORED_FROM
        )
        defense_frames.append(points)
        season = int(points["season"].to_numpy().max())
        past = points.filter((pl.col("season") < season) | (pl.col("week") < current))
        ahead = games.filter((pl.col("season") == season) & (pl.col("week") >= current)).select(
            pl.col("team").alias("unit"),
            "team",
            "season",
            "week",
            pl.col("opp_implied").alias("implied"),
            "roof",
        )
        d_hist = past.rename({"team": "unit", "opp_implied": "implied"})
        d_hist, d_ahead = sm.with_form(d_hist, ahead)
        d_proj, d_rmse = _unit_projection(
            d_hist, d_ahead, sm.DEF_FEATURES, False, "DEF", lid, id_map
        )
        projections.append(d_proj)
        report[f"{lg['league_key']} DEF rmse (model, mean)"] = d_rmse

        k_hist = kickers.filter(
            (pl.col("league_id") == lid)
            & (pl.col("season") >= SCORED_FROM)
            & (pl.col("season_type") == "REG")
            & ((pl.col("season") < season) | (pl.col("week") < current))
        )
        k_hist = k_hist.select(
            pl.col("gsis_id").alias("unit"),
            "team",
            "opponent_team",
            "season",
            "week",
            "points",
            pl.col("team_implied").alias("implied"),
            "roof",
        )
        k_ahead = active_k.join(
            coded.filter((pl.col("season") == season) & (pl.col("week") >= current)),
            left_on="nfl_team",
            right_on="team",
        ).select(
            pl.col("gsis_id").alias("unit"),
            pl.col("nfl_team").alias("team"),
            pl.col("opponent").alias("opponent_team"),
            "season",
            "week",
            pl.col("team_implied").alias("implied"),
            "roof",
        )
        k_hist, k_ahead = sm.with_form(k_hist, k_ahead)
        usage = sm.kicker_trailing(player_stats, k_ahead.rename({"unit": "gsis_id"}))
        k_hist = _with_k_features(k_hist, teams, usage)
        k_ahead = _with_k_features(k_ahead, teams, usage)
        k_proj, k_rmse = _unit_projection(k_hist, k_ahead, sm.K_FEATURES, True, "K", lid, id_map)
        projections.append(k_proj)
        report[f"{lg['league_key']} K rmse (model, mean)"] = k_rmse
    store.write_table("defense_points", pl.concat(defense_frames))
    out = pl.concat(projections).select("league_id", "kind", "unit", "team", "week", "projection")
    store.write_table("streaming_projection", out)
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    snapshot = out.with_columns(pl.lit(stamp).alias("fetched_at")).select(
        *store.SCHEMAS["streaming_snapshots"]
    )
    store.write_table(
        "streaming_snapshots", store.with_archive("streaming_snapshots", snapshot), "archive"
    )
    return report


def main() -> None:
    for name, (model, mean) in run().items():
        print(f"{name}: {model:.2f} vs {mean:.2f}")


if __name__ == "__main__":
    main()
