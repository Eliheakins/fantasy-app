"""Baseline projections: each player's recent expected points, shrunk to a position average.

For a player and a target game, the projection uses only games played BEFORE it:
  shrunk(x)  = (n * ewma(x) + K * position_prior) / (n + K), n = games played (capped)
  form       = 0.5 * shrunk(expected points) + 0.5 * shrunk(actual points)
  projection = form * context, where context = (team implied total / season average) ** 0.25

Expected points come from nflverse's opportunity model (touchdown and yardage luck removed),
scored under each league's rules. Players with no history get the position prior. Constants were
tuned in a 2019 to 2023 / 2024 to 2025 test (docs/decisions.md). Quarterbacks, running backs,
receivers and tight ends only; kickers and defenses are projected in stages/streaming.py.

Run: uv run python -m fantasy.stages.project
"""

import json

import polars as pl

from fantasy import store
from fantasy.scoring import expected_points_expr
from fantasy.store import SKILL, week_index

HALF_LIFE = 4.0  # games
SHRINK_K = 3.0  # games of prior weight
EXPECTED_WEIGHT = 0.5  # blend of expected and actual points; 0.5 won a 2019-2023 / 2024-2025 test
N_CAP = 10
CONTEXT_EXPONENT = 0.25  # 0.5 over-reacts to the implied total; see docs/decisions.md
FIRST_PROJECTED_SEASON = 2019  # the first season with a prior season to lean on
LAST_WEEK = 17
POSITIONS = SKILL
GROUP = ["league_id", "gsis_id"]
MAX_UNSCORED_SHARE = 0.05  # expected-points rows with no scored row (a position label differs)


def expected_frame(
    opp: pl.DataFrame, player_points: pl.DataFrame, leagues: pl.DataFrame
) -> pl.DataFrame:
    """One row per league and player-game: expected points and actual points."""
    frames = []
    for lg in leagues.iter_rows(named=True):
        actual = player_points.filter(pl.col("league_id") == lg["league_id"]).select(
            "gsis_id", "season", "week", "points"
        )
        scoring = json.loads(lg["scoring_settings"])
        expected = (
            opp.filter(pl.col("position").is_in(POSITIONS))
            .select(
                pl.col("player_id").alias("gsis_id"),
                "season",
                "week",
                "position",
                pl.col("posteam").alias("team"),
                expected_points_expr(scoring).alias("exp_pts"),
            )
            .unique(subset=["gsis_id", "season", "week"], keep="first", maintain_order=True)
        )
        # an expected-points row with no scored row (nflverse labels the position differently in
        # the two sources, e.g. a CB who plays WR) has no actual points: drop it, not score it 0
        matched = expected.join(actual, on=["gsis_id", "season", "week"], how="inner")
        dropped = expected.height - matched.height
        if dropped:
            print(f"expected_frame: league {lg['league_id']}: {dropped} unscored rows dropped")
        if dropped > MAX_UNSCORED_SHARE * expected.height:
            raise ValueError(f"{dropped} of {expected.height} expected-points rows have no points")
        frames.append(matched.with_columns(pl.lit(lg["league_id"]).alias("league_id")))
    return pl.concat(frames)


def position_prior(exp: pl.DataFrame) -> pl.DataFrame:
    """Prior for season s: the position's mean expected points in season s-1 (own if none)."""
    keys = ["league_id", "position", "season"]
    means = exp.group_by(keys).agg(pl.col("exp_pts").mean().alias("own"))
    last = means.with_columns(pl.col("season") + 1).rename({"own": "last"})
    return means.join(last, on=keys, how="left").select(*keys, prior=pl.coalesce("last", "own"))


def build_form(exp: pl.DataFrame, prior: pl.DataFrame) -> pl.DataFrame:
    """Per player-game: form AFTER that game (it is used for later games only)."""
    df = exp.sort(*GROUP, "season", "week").with_columns(
        ewma_exp=pl.col("exp_pts").ewm_mean(half_life=HALF_LIFE).over(GROUP),
        ewma_actual=pl.col("points").ewm_mean(half_life=HALF_LIFE).over(GROUP),
        n_games=pl.int_range(1, pl.len() + 1).over(GROUP).clip(upper_bound=N_CAP),
    )
    n, prior_pts = pl.col("n_games"), pl.col("prior")
    shrunk_exp = (n * pl.col("ewma_exp") + SHRINK_K * prior_pts) / (n + SHRINK_K)
    shrunk_actual = (n * pl.col("ewma_actual") + SHRINK_K * prior_pts) / (n + SHRINK_K)
    return (
        df.join(prior, on=["league_id", "position", "season"], how="left")
        .with_columns(form=EXPECTED_WEIGHT * shrunk_exp + (1 - EXPECTED_WEIGHT) * shrunk_actual)
        .select(*store.SCHEMAS["player_form"])
    )


def project_targets(
    targets: pl.DataFrame,
    form: pl.DataFrame,
    prior: pl.DataFrame,
    games: pl.DataFrame,
    horizon: int = 1,
) -> pl.DataFrame:
    """targets: league_id, gsis_id, season, week, position, team. Uses only earlier games.

    horizon 1 projects from games before the target. A larger horizon uses only games at least
    that many weeks earlier and a neutral context, because lines do not exist that far ahead.
    """
    index = week_index()
    latest = form.select(
        *GROUP,
        index.alias("t"),
        pl.col("season").alias("as_of_season"),
        pl.col("week").alias("as_of_week"),
        "form",
        "ewma_actual",
    ).sort("t")
    avg_implied = games.group_by("season").agg(pl.col("team_implied").mean().alias("avg_implied"))
    context = games.select("season", "week", "team", "team_implied")
    joined = (
        targets.with_columns((index - (horizon - 1)).alias("t"))
        .sort("t")
        .join_asof(latest, on="t", by=GROUP, strategy="backward", allow_exact_matches=False)
        .join(prior, on=["league_id", "position", "season"], how="left")
        .join(context, on=["season", "week", "team"], how="left")
        .join(avg_implied, on="season", how="left")
    )
    ctx = ((pl.col("team_implied") / pl.col("avg_implied")) ** CONTEXT_EXPONENT).fill_null(1.0)
    if horizon > 1:
        ctx = pl.lit(1.0)
    return joined.with_columns(
        has_history=pl.col("form").is_not_null(),
        context=ctx,
        projection=pl.coalesce("form", "prior") * ctx,
    )


def history_targets(exp: pl.DataFrame) -> pl.DataFrame:
    return exp.filter(pl.col("season") >= FIRST_PROJECTED_SEASON).select(
        *GROUP, "season", "week", "position", "team"
    )


def future_targets(
    form: pl.DataFrame,
    current_teams: pl.DataFrame,
    rostered: pl.DataFrame,
    games: pl.DataFrame,
    first_week: int | None = None,
) -> pl.DataFrame:
    """Remaining regular-season games for active players. Bye weeks have no game row.

    current_teams: gsis_id, team, position (from Sleeper). rostered: league_id, gsis_id, the
    players on every team's roster in each league (rivals' rookies and new signings too), who get
    the position prior if they have no history. first_week is the league's current week: a
    Thursday game puts it in the data before the other teams have played, so the latest week with
    any game is not a safe start. Games that are already final (they have a score) are dropped.
    """
    ordered = form.sort("season", "week")
    season, week = ordered.select("season", "week").tail(1).row(0)
    last = (
        ordered.group_by(GROUP)
        .agg(
            pl.col("season").last().alias("last_season"),
            pl.col("position").last(),
            pl.col("team").last(),
        )
        .filter(pl.col("last_season") >= season - 1)
        .select(*GROUP, "position", "team")
    )
    extra = (
        rostered.join(last.select(GROUP), on=GROUP, how="anti")
        .join(current_teams.select("gsis_id", "position"), on="gsis_id")
        .filter(pl.col("position").is_in(POSITIONS))  # K and DEF are projected in streaming.py
        .with_columns(team=pl.lit(None, dtype=pl.String))
        .select(*GROUP, "position", "team")
    )
    now = current_teams.select("gsis_id", pl.col("team").alias("now"))
    players = (
        pl.concat([last, extra])
        .join(now, on="gsis_id", how="left")
        .filter(pl.col("now").is_not_null())  # a player with no current team plays no games
        .drop("team")
        .rename({"now": "team"})
    )
    start = week + 1 if first_week is None else first_week
    weeks = pl.DataFrame({"week": list(range(start, LAST_WEEK + 1))}, schema={"week": pl.Int64})
    # a game has a score only once it is final, so Sunday's finished games drop out while Monday
    # night's stays, and an inactive player (no form row) does not get a game that is over
    unplayed = games.filter((pl.col("game_type") == "REG") & pl.col("points_for").is_null())
    return (
        players.join(weeks, how="cross")
        .with_columns(season=pl.lit(season, dtype=pl.Int64))
        .join(unplayed.select("season", "week", "team"), on=["season", "week", "team"])
        .select(*GROUP, "season", "week", "position", "team")
    )


def current_and_rostered() -> tuple[pl.DataFrame, pl.DataFrame]:
    """Each player's current team and position, and the players on my rosters."""
    id_map = store.read_table("id_map")
    positions = store.read_table("sleeper_players", "raw").select("sleeper_id", "position")
    current = (
        id_map.filter(pl.col("gsis_id").is_not_null())
        .join(positions, on="sleeper_id")
        .select("sleeper_id", "gsis_id", pl.col("nfl_team").alias("team"), "position")
        .sort("gsis_id", "sleeper_id")
        .unique(subset="gsis_id", keep="first", maintain_order=True)
        .drop("sleeper_id")
    )
    on_rosters = store.read_table("rosters", "raw").join(
        id_map.select("sleeper_id", "gsis_id"), on="sleeper_id", how="left"
    )
    for league_id, n in (
        on_rosters.filter(pl.col("gsis_id").is_null()).group_by("league_id").len().iter_rows()
    ):
        print(f"league {league_id}: {n} rostered players have no nflverse id, so no projection")
    rostered = (
        on_rosters.filter(pl.col("gsis_id").is_not_null())
        .select("league_id", "gsis_id")
        .unique(maintain_order=True)
    )
    return current, rostered


def unprojected_rostered(
    rostered: pl.DataFrame, current: pl.DataFrame, future: pl.DataFrame
) -> pl.DataFrame:
    """Per league, rostered skill players with a current team but no future projection row."""
    skill = current.filter(pl.col("position").is_in(POSITIONS) & pl.col("team").is_not_null())
    have = future.select(GROUP).unique()
    return (
        rostered.join(skill.select("gsis_id"), on="gsis_id")
        .join(have, on=GROUP, how="anti")
        .group_by("league_id")
        .len()
        .sort("league_id")
    )


def run() -> dict[str, int]:
    leagues = store.read_table("leagues", "raw")
    exp = expected_frame(
        store.read_table("nfl_ff_opportunity", "raw"), store.read_table("player_points"), leagues
    )
    prior = position_prior(exp)
    form = build_form(exp, prior)
    games = store.read_table("team_games")

    history = project_targets(history_targets(exp), form, prior, games)
    current, rostered = current_and_rostered()
    current_week = int(leagues["current_week"].max())  # type: ignore[arg-type]
    future_rows = future_targets(form, current, rostered, games, first_week=current_week)
    future = project_targets(future_rows, form, prior, games)
    for league_id, n in unprojected_rostered(rostered, current, future_rows).iter_rows():
        print(f"league {league_id}: {n} rostered skill players have no future projection")
    both = [
        history.with_columns(is_future=pl.lit(False)),
        future.with_columns(is_future=pl.lit(True)),
    ]
    out = pl.concat(both).select(*store.SCHEMAS["proj_baseline"])
    store.write_tables({"player_form": form, "proj_baseline": out})
    return {"player_form": form.height, "history": history.height, "future": future.height}


def main() -> None:
    for name, rows in run().items():
        print(f"{name}: {rows} rows")


if __name__ == "__main__":
    main()
