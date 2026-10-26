"""Teammate vacancy for a game, from that game's injury report: features of the learned model.

For a player and a target game: the share of the team's targets and carries, and of his
position's snaps, held by skill teammates listed Out or Doubtful; the same for Questionable
teammates, each weighted by the chance a Questionable player sits given his final practice; and
an effective depth rank (the game's chart rank minus teammates at his position listed Out or
Doubtful who rank above him). A teammate's shares are his weighted averages (half-life 4 games)
over games strictly before the target game (`lags.lag_asof`); the report is the game's own.

History uses nflverse's final report (Friday, Saturday for a Monday game). For the next game
only, a team whose final report has no game status yet uses Sleeper's Out players instead
(`sleeper_report`, `with_stand_in`; practice unknown): Sleeper's Questionable and Doubtful agree
too poorly with the final report to stand in for it, and IR, PUP and the other long-term
designations are not game statuses, as in history. Weeks with no report are projected by a model
without these columns (`learn.predict_future`). A teammate vacates only the usage he had with the
team he is listed for, so a traded player's old role does not count. research/news_features_check.py
has the held-out test (docs/decisions.md).
"""

import polars as pl

from fantasy.stages.crosswalk import norm_team
from fantasy.stages.injuries import PRACTICE
from fantasy.stages.lags import lag_asof
from fantasy.stages.outlook import usage_table as share_table
from fantasy.store import SKILL

KEY = ["gsis_id", "season", "week"]
STATUSES = ("Out", "Doubtful", "Questionable")
OUT_STATUSES = ("Out", "Doubtful")
STAND_IN_STATUSES = ("Out",)
USAGE = ("tgt", "car", "snap")
VAC_COLUMNS = [f"vac_{kind}_{c}" for kind in ("out", "q") for c in USAGE] + ["eff_depth"]
FIRST_WEIGHT_SEASON = 2018


def report_table(injuries: pl.DataFrame) -> pl.DataFrame:
    """KEY, team, position, status (Out, Doubtful, Questionable or null) and practice (Full,
    Limited, DNP or null) from nflverse's final regular-season report of each game week."""
    return (
        injuries.filter(pl.col("game_type") == "REG")
        .unique(KEY, keep="first", maintain_order=True)
        .select(
            *KEY,
            "team",
            "position",
            pl.when(pl.col("report_status").is_in(STATUSES))
            .then(pl.col("report_status"))
            .alias("status"),
            pl.col("practice_status").replace_strict(PRACTICE, default=None).alias("practice"),
        )
    )


def sleeper_report(
    players: pl.DataFrame, id_map: pl.DataFrame, season: int, week: int
) -> pl.DataFrame:
    """The serve-time stand-in for a week without a final report, in `report_table`'s schema:
    Sleeper's Out players (players: sleeper_id, position, team, injury_status), practice unknown,
    team codes as nflverse writes them, gsis ids from the crosswalk."""
    return (
        players.filter(pl.col("injury_status").is_in(STAND_IN_STATUSES))
        .drop("gsis_id", strict=False)  # Sleeper's own column is mostly empty
        .join(id_map.select("sleeper_id", "gsis_id"), on="sleeper_id", how="inner")
        .filter(pl.col("gsis_id").is_not_null())
        .select(
            "gsis_id",
            pl.lit(season, pl.Int64).alias("season"),
            pl.lit(week, pl.Int64).alias("week"),
            pl.col("team").map_elements(norm_team, return_dtype=pl.String).alias("team"),
            "position",
            pl.col("injury_status").alias("status"),
            pl.lit(None, pl.String).alias("practice"),
        )
        .unique("gsis_id", keep="first", maintain_order=True)
    )


def unmapped_out(players: pl.DataFrame, id_map: pl.DataFrame) -> int:
    """Sleeper's Out players the crosswalk has no gsis id for (they cannot stand in)."""
    out = players.filter(pl.col("injury_status").is_in(STAND_IN_STATUSES)).select("sleeper_id")
    mapped = id_map.filter(pl.col("gsis_id").is_not_null()).select("sleeper_id")
    return out.join(mapped, on="sleeper_id", how="anti").height


def _issued(report: pl.DataFrame, season: int, week: int) -> list[str]:
    this_week = (pl.col("season") == season) & (pl.col("week") == week)
    return report.filter(this_week & pl.col("status").is_not_null())["team"].unique().to_list()


def report_sources(
    report: pl.DataFrame, season: int, week: int, teams: list[str]
) -> dict[str, str]:
    """Team -> 'final' when its final report for the week has game statuses, else 'sleeper'."""
    issued = set(_issued(report, season, week))
    return {t: "final" if t in issued else "sleeper" for t in teams}


def with_stand_in(
    report: pl.DataFrame, stand_in: pl.DataFrame, season: int, week: int
) -> pl.DataFrame:
    """`report` with the week's rows of each team that has no game status on the final report
    yet replaced by the stand-in's rows for that team."""
    this_week = (pl.col("season") == season) & (pl.col("week") == week)
    issued = _issued(report, season, week)
    keep = report.filter(~this_week | pl.col("team").is_in(issued))
    added = stand_in.filter(this_week & ~pl.col("team").is_in(issued))
    return pl.concat([keep, added.select(keep.columns)]).unique(
        KEY, keep="first", maintain_order=True
    )


def sit_weights(
    report: pl.DataFrame, snaps: pl.DataFrame, last_season: int
) -> dict[str | None, float]:
    """Practice (or None, unknown) -> share of Questionable skill players who had no offensive
    snaps, seasons FIRST_WEIGHT_SEASON to `last_season`. With no such rows (a fresh or partial
    table) Questionable teammates count for nothing, with a warning."""
    played = (
        snaps.filter(pl.col("offense_snaps") > 0).select(KEY).unique().with_columns(p=pl.lit(1.0))
    )
    rows = (
        report.filter(
            (pl.col("status") == "Questionable")
            & pl.col("position").is_in(SKILL)
            & pl.col("season").is_between(FIRST_WEIGHT_SEASON, last_season)
        )
        .join(played, on=KEY, how="left")
        .with_columns(pl.col("p").fill_null(0.0))
    )
    if rows.is_empty():
        print(
            "vacancy: WARNING no Questionable report rows to weigh by; "
            "Questionable teammates count 0"
        )
        return {None: 0.0}
    by_practice = rows.group_by("practice").agg(pl.col("p").mean())
    weights: dict[str | None, float] = {
        r["practice"]: 1.0 - r["p"] for r in by_practice.iter_rows(named=True)
    }
    weights[None] = 1.0 - float(rows["p"].mean())  # type: ignore[arg-type]
    return weights


def usage_table(stats: pl.DataFrame, team_stats: pl.DataFrame, snaps: pl.DataFrame) -> pl.DataFrame:
    """KEY, team, tgt (target share), car (carry share), snap (offense share) per player-game."""
    shares = (
        share_table(stats, team_stats)
        .select(
            *KEY, "team", pl.col("target_share").alias("tgt"), pl.col("carry_share").alias("car")
        )
        .unique(KEY, keep="first", maintain_order=True)
    )
    snap = (
        snaps.filter(pl.col("gsis_id").is_not_null())
        .select(
            *KEY,
            pl.col("team").alias("_team"),
            pl.col("offense_pct").cast(pl.Float64).alias("snap"),
        )
        .unique(KEY, keep="first", maintain_order=True)
    )
    return (
        shares.join(snap, on=KEY, how="full", coalesce=True)
        .with_columns(pl.coalesce("team", "_team").alias("team"))
        .select(*KEY, "team", *USAGE)
    )


def _who() -> pl.Expr:
    return pl.concat_str("gsis_id", "team", separator="|").alias("_who")


def _listed(report: pl.DataFrame, weights: dict[str | None, float]) -> pl.DataFrame:
    """Skill players with a game status, `kind` out or q and their weight `w`."""
    by_practice = {k: v for k, v in weights.items() if k is not None}
    is_out = pl.col("status").is_in(OUT_STATUSES)
    return report.filter(
        pl.col("status").is_not_null() & pl.col("position").is_in(SKILL)
    ).with_columns(
        pl.when(is_out).then(pl.lit("out")).otherwise(pl.lit("q")).alias("kind"),
        pl.when(is_out)
        .then(1.0)
        .otherwise(
            pl.col("practice")
            .replace_strict(by_practice, default=weights[None], return_dtype=pl.Float64)
            .fill_null(weights[None])
        )
        .alias("w"),
    )


def vacancy_features(
    targets: pl.DataFrame,
    report: pl.DataFrame,
    usage: pl.DataFrame,
    weights: dict[str | None, float],
    depth: pl.DataFrame,
) -> pl.DataFrame:
    """targets (KEY, team, position, depth_rank) with VAC_COLUMNS."""
    listed = _listed(report, weights).with_columns(_who())
    lagged = lag_asof(listed, usage.with_columns(_who()), "_who", list(USAGE), "u").with_columns(
        [(pl.col(f"u_{c}").fill_null(0.0) * pl.col("w")).alias(c) for c in USAGE]
    )
    team_keys = ["team", "season", "week"]
    out = targets
    for kind in ("out", "q"):
        part = lagged.filter(pl.col("kind") == kind)
        team = part.group_by(team_keys).agg(pl.col("tgt", "car").sum().name.prefix("_t_"))
        position = part.group_by(*team_keys, "position").agg(pl.col("snap").sum().alias("_t_snap"))
        own = part.select(*KEY, *[pl.col(c).alias(f"_o_{c}") for c in USAGE])
        out = (
            out.join(team, on=team_keys, how="left")
            .join(position, on=[*team_keys, "position"], how="left")
            .join(own, on=KEY, how="left")
            .with_columns(
                [
                    (pl.col(f"_t_{c}").fill_null(0.0) - pl.col(f"_o_{c}").fill_null(0.0))
                    .clip(lower_bound=0.0)
                    .alias(f"vac_{kind}_{c}")
                    for c in USAGE
                ]
            )
            .drop([f"_{s}_{c}" for s in ("t", "o") for c in USAGE])
        )
    chart = depth.select(*KEY, pl.col("depth_rank").alias("_rank")).unique(KEY, keep="first")
    mates = (
        listed.filter(pl.col("kind") == "out")
        .join(chart, on=KEY, how="inner")
        .select(pl.col("gsis_id").alias("_mate"), *team_keys, "position", "_rank")
    )
    above = (
        targets.select(*KEY, "team", "position", "depth_rank")
        .join(mates, on=[*team_keys, "position"], how="inner")
        .filter((pl.col("_mate") != pl.col("gsis_id")) & (pl.col("_rank") < pl.col("depth_rank")))
        .group_by(KEY)
        .agg(pl.len().cast(pl.Float64).alias("_above"))
    )
    return (
        out.join(above, on=KEY, how="left")
        .with_columns((pl.col("depth_rank") - pl.col("_above").fill_null(0.0)).alias("eff_depth"))
        .drop("_above")
    )
