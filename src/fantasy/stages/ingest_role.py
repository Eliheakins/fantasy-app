"""Role and context data from nflverse: depth charts, weekly rosters, advanced stats, team pace and
FantasyPros weekly expert rankings, normalized to one row per player (or team) and week.

Everything here is known before kickoff or lagged by the learned stage, and each dataset was
tested for held-out gain before it was added (docs/decisions.md). The FantasyPros rankings are
private-use only: they are written under the gitignored data/ and must not be committed.

The loaders are called from `ingest_nfl`; the normalizers are pure and tested.
"""

from functools import reduce

import nflreadpy as nfl
import polars as pl

from fantasy import store

SEASONS = list(range(2018, 2027))
SKILL = ["QB", "RB", "WR", "TE"]
OLD_DEPTH_LAST_SEASON = 2024  # the weekly depth chart; later seasons are dated snapshots
UNDRAFTED_PICK = 300.0
RANKING_MAX_GAP_DAYS = 9  # a scrape counts for a week only this close before its first game
KEY = ["gsis_id", "season", "week"]


def old_depth(old: pl.DataFrame) -> pl.DataFrame:
    """Weekly depth chart (2018 to 2024): the best offensive depth slot a player held that week."""
    return (
        old.filter(
            (pl.col("game_type") == "REG")
            & (pl.col("formation") == "Offense")
            & pl.col("position").is_in(SKILL)
        )
        .with_columns(pl.col("depth_team").cast(pl.Float64, strict=False))
        .group_by("gsis_id", "season", "week")
        .agg(pl.col("depth_team").min().alias("depth_rank"))
        .with_columns(pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64))
    )


def new_depth(snapshots: pl.DataFrame, games: pl.DataFrame) -> pl.DataFrame:
    """Dated depth chart snapshots (2025 on): for each team's game the latest snapshot at or before
    the game day, so a chart published after the game never leaks in.

    snapshots: team, dt (UTC time string), gsis_id, pos_abb, pos_rank. games: season, week, team,
    gameday (date string)."""
    snaps = snapshots.filter(pl.col("pos_abb").is_in(SKILL)).with_columns(
        pl.col("dt").str.to_datetime(time_zone="UTC").dt.replace_time_zone(None).alias("taken")
    )
    kicks = games.select(
        "season", "week", "team", pl.col("gameday").str.to_date().cast(pl.Datetime).alias("kick")
    ).sort("kick")
    taken = snaps.select("team", "taken").unique().sort("taken")
    picked = kicks.join_asof(
        taken, left_on="kick", right_on="taken", by="team", strategy="backward"
    )
    unmatched = picked.filter(pl.col("taken").is_null())["team"].unique().sort().to_list()
    if unmatched:  # most likely a team abbreviation that differs between the two sources
        raise ValueError(f"no depth chart snapshot before the game for teams {unmatched}")
    ranks = snaps.select(
        "team", "taken", "gsis_id", pl.col("pos_rank").cast(pl.Float64).alias("depth_rank")
    )
    return (
        picked.join(ranks, on=["team", "taken"])
        .group_by("gsis_id", "season", "week")
        .agg(pl.col("depth_rank").min())
        .with_columns(pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64))
    )


def roster_features(roster: pl.DataFrame) -> pl.DataFrame:
    """Age on September 1 of the season, years in the league and draft pick (late if undrafted)."""
    return (
        roster.filter((pl.col("game_type") == "REG") & pl.col("gsis_id").is_not_null())
        .unique(KEY, keep="first")
        .select(
            *KEY,
            (
                (pl.date(pl.col("season"), 9, 1) - pl.col("birth_date")).dt.total_days() / 365.25
            ).alias("age"),
            pl.col("years_exp").cast(pl.Float64),
            pl.col("draft_number").cast(pl.Float64).fill_null(UNDRAFTED_PICK).alias("draft_pick"),
        )
        .with_columns(pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64))
    )


def matched_rankings(rankings: pl.DataFrame, calendar: pl.DataFrame) -> pl.DataFrame:
    """Each weekly ranking scrape is matched to the next game week (within RANKING_MAX_GAP_DAYS of
    its first game) and the last scrape before that week's first game is the one kept.

    rankings: id, scrape_date (date string), ecr, sd, best, worst. calendar: season, week,
    first_game (date)."""
    ranked = rankings.with_columns(pl.col("scrape_date").str.to_date().alias("scraped"))
    scrapes = ranked.select("scraped").unique().sort("scraped")
    matched = scrapes.join_asof(
        calendar.sort("first_game"), left_on="scraped", right_on="first_game", strategy="forward"
    ).filter(
        (pl.col("first_game") - pl.col("scraped"))
        .dt.total_days()
        .is_between(1, RANKING_MAX_GAP_DAYS)
    )  # a scrape on game day may follow kickoff, so it does not count
    latest = matched.group_by("season", "week").agg(pl.col("scraped").last())
    keep = latest.join(matched, on=["season", "week", "scraped"])
    return (
        ranked.join(keep, on="scraped")
        .select(
            "id",
            pl.col("season").cast(pl.Int64),
            pl.col("week").cast(pl.Int64),
            pl.col("ecr").cast(pl.Float64),
            pl.col("sd").cast(pl.Float64),
            (pl.col("worst") - pl.col("best")).cast(pl.Float64).alias("range"),
        )
        .unique(["id", "season", "week"], keep="first")
    )


def schedule_games(seasons: list[int]) -> pl.DataFrame:
    """One row per team and regular-season game: season, week, team, gameday."""
    s = nfl.load_schedules(seasons).filter(pl.col("game_type") == "REG")
    return pl.concat(
        [
            s.select("season", "week", pl.col(side).alias("team"), "gameday")
            for side in ("home_team", "away_team")
        ]
    )


def load_depth() -> pl.DataFrame:
    old = nfl.load_depth_charts([s for s in SEASONS if s <= OLD_DEPTH_LAST_SEASON])
    new = nfl.load_depth_charts([s for s in SEASONS if s > OLD_DEPTH_LAST_SEASON])
    games = schedule_games([s for s in SEASONS if s > OLD_DEPTH_LAST_SEASON])
    return pl.concat([old_depth(old), new_depth(new, games)])


def load_rosters() -> pl.DataFrame:
    return roster_features(nfl.load_rosters_weekly(SEASONS))


def load_advanced() -> pl.DataFrame:
    """Pro-Football-Reference receiving extras and Next Gen Stats for receivers, rushers and
    passers, outer-joined by player-week with source-prefixed columns."""
    ids = nfl.load_ff_playerids().select("pfr_id", "gsis_id").drop_nulls().unique("pfr_id")
    pfr = (
        nfl.load_pfr_advstats(SEASONS, stat_type="rec", summary_level="week")
        .filter(pl.col("game_type") == "REG")
        .join(ids, left_on="pfr_player_id", right_on="pfr_id")
    )
    pfr_cols = [
        "rushing_broken_tackles",
        "receiving_broken_tackles",
        "receiving_drop_pct",
        "receiving_rat",
    ]
    parts = [pfr.select(*KEY, *[pl.col(c).cast(pl.Float64).alias(f"pfr_{c}") for c in pfr_cols])]
    for kind, prefix in (("receiving", "ngsrec"), ("rushing", "ngsrus"), ("passing", "ngspas")):
        ngs = nfl.load_nextgen_stats(SEASONS, stat_type=kind).filter(pl.col("week") > 0)
        wanted = [
            c[len(prefix) + 1 :]
            for c in store.SCHEMAS["nfl_advanced"]
            if c.startswith(f"{prefix}_")
        ]
        parts.append(
            ngs.select(
                pl.col("player_gsis_id").alias("gsis_id"),
                "season",
                "week",
                *[pl.col(c).cast(pl.Float64).alias(f"{prefix}_{c}") for c in wanted],
            )
        )
    keyed = [
        p.drop_nulls("gsis_id")
        .with_columns(pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64))
        .unique(KEY)
        for p in parts
    ]
    return reduce(lambda a, b: a.join(b, on=KEY, how="full", coalesce=True), keyed)


def load_pace() -> pl.DataFrame:
    """Team plays, dropbacks, pass rate over expected and EPA per play for each game."""
    rows = []
    for season in SEASONS:
        try:
            pbp = nfl.load_pbp([season])
        except Exception as error:  # nflverse may not have published the season yet
            print(f"team pace: skipping {season}: {type(error).__name__}: {str(error)[:80]}")
            continue
        plays = pbp.filter(
            (pl.col("season_type") == "REG")
            & ((pl.col("pass") == 1) | (pl.col("rush") == 1))
            & pl.col("posteam").is_not_null()
        )
        rows.append(
            plays.group_by("posteam", "season", "week")
            .agg(
                pl.len().alias("plays"),
                pl.col("qb_dropback").sum().alias("dropbacks"),
                pl.col("pass_oe").mean().alias("pass_oe"),
                pl.col("epa").mean().alias("team_epa"),
            )
            .rename({"posteam": "team"})
        )
    if not rows:
        raise RuntimeError("no play-by-play season could be loaded")
    return pl.concat(rows).with_columns(
        pl.col("season").cast(pl.Int64), pl.col("week").cast(pl.Int64)
    )


def load_ecr() -> pl.DataFrame:
    """FantasyPros weekly position and overall rankings (private use), one row per player-week."""
    ids = (
        nfl.load_ff_playerids()
        .select(pl.col("fantasypros_id").cast(pl.String).alias("id"), "gsis_id")
        .drop_nulls()
        .unique("id")
    )
    s = nfl.load_schedules(SEASONS).filter(pl.col("game_type") == "REG")
    calendar = (
        s.with_columns(pl.col("gameday").str.to_date().alias("first_game"))
        .group_by("season", "week")
        .agg(pl.col("first_game").min())
    )
    allrank = nfl.load_ff_rankings(type="all")
    parts = []
    for kind, prefix in (("wp", "ecr_pos"), ("wo", "ecr_all")):
        raw = allrank.filter(pl.col("ecr_type") == kind).with_columns(pl.col("id").cast(pl.String))
        matched = matched_rankings(raw, calendar).join(ids, on="id").drop_nulls("gsis_id")
        parts.append(
            matched.select(
                *KEY,
                pl.col("ecr").alias(prefix),
                pl.col("sd").alias(f"{prefix}_sd"),
                pl.col("range").alias(f"{prefix}_range"),
            ).unique(KEY, keep="first")
        )
    return reduce(lambda a, b: a.join(b, on=KEY, how="full", coalesce=True), parts)
