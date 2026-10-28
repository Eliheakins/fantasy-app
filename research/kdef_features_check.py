"""K and DEF: do features beyond form and the game's implied total improve the projection?

The current K and DEF projection (`streaming.project_units`: recent form shrunk toward the league
mean, plus a slope on the implied total and, for K, a dome bonus) beat the league average by 2% to
5% for DEF and not at all for K (decisions.md, 2026-10-23). Untested before this script, from data
already in the repo: the opposing offense's and the unit's own team's trailing sacks, interceptions,
EPA, sack rate and pace (`nfl_team_stats`, `nfl_team_efficiency`, `nfl_team_pace`); spread and home
field; the kicker's own trailing field-goal attempts and long-kick mix (`nfl_player_stats`); the
opposing defense's trailing points allowed; and FantasyPros position rankings for K (`nfl_ecr`,
about 70% of K games from 2021). Not available for DEF: rankings (no ids), FFToday and prop lines
(no K or DEF rows), weather before week 5 only.

Arms, each refit before every week on earlier weeks only (2019 on, rows scored from 2024):
  current   `streaming.project_units`, exactly as the stage runs it
  stack     ridge on [form, implied] (+ dome for K): the current ingredients refit jointly
  +<group>  stack plus one feature group
  +all      stack plus every group
Ridge uses standardized features and a fixed penalty (RIDGE_LAMBDA, not tuned). Trailing features
(`streaming_model.trailing`) are exponentially weighted means of the unit's earlier games (half-life
6 games, shrunk 3 games toward the mean of all earlier rows), so every feature uses only games
before the target.

Rule fixed before the run: a feature set ships for a unit kind (DEF, K) if, in both leagues, its
RMSE is below `current` and the paired per-week t of the squared-error difference is -2 or lower.
The ECR arm is scored on the K games that have a ranking and compared with `current` on the same
games.

Run from the repo root: uv run python research/kdef_features_check.py
"""

import json

import numpy as np
import polars as pl

from fantasy import store
from fantasy.stages import streaming
from fantasy.stages.streaming_model import ridge_predict, trailing

FIT_FROM = 2019
SCORE_FROM = 2024
MIN_FIT_ROWS = 200
TEAM_STATS = (
    "sacks_suffered",
    "passing_interceptions",
    "attempts",
    "def_sacks",
    "def_interceptions",
)
TEAM_EFF = ("pass_epa", "sack_rate")
TEAM_PACE = ("plays", "pass_oe", "team_epa")
KEY = ["team", "season", "week"]


def team_features() -> pl.DataFrame:
    """Trailing team features before each team-game, plus the game's spread and home flag."""
    stats = store.read_table("nfl_team_stats", "raw").filter(pl.col("season_type") == "REG")
    eff = store.read_table("nfl_team_efficiency", "raw").select(*KEY, *TEAM_EFF)
    pace = store.read_table("nfl_team_pace", "raw").select(*KEY, *TEAM_PACE)
    games = store.read_table("team_games").with_columns(
        pl.col("team").replace(streaming.SCHEDULE_TEAM_CODES)
    )
    games = games.select(*KEY, "points_against", "points_for", "spread", "is_home")
    table = (
        stats.select(*KEY, *TEAM_STATS)
        .join(eff, on=KEY, how="left")
        .join(pace, on=KEY, how="left")
        .join(games, on=KEY, how="left")
    )
    cols = [*TEAM_STATS, *TEAM_EFF, *TEAM_PACE, "points_against", "points_for"]
    return trailing(table, "team", cols).select(
        *KEY, "spread", pl.col("is_home").cast(pl.Float64), *[f"{c}_tr" for c in cols]
    )


def prefixed(teams: pl.DataFrame, prefix: str) -> pl.DataFrame:
    """The trailing columns under `prefix` (d_ own team, o_ opponent) and a prefixed team key."""
    tr = [c for c in teams.columns if c.endswith("_tr")]
    renamed = {c: f"{prefix}{c}" for c in tr} | {"team": f"{prefix}team"}
    return teams.select("team", "season", "week", *tr).rename(renamed)


DEF_GROUPS = {
    "opp_offense": [
        "o_sacks_suffered_tr",
        "o_passing_interceptions_tr",
        "o_pass_epa_tr",
        "o_sack_rate_tr",
        "o_plays_tr",
        "o_points_for_tr",
    ],
    "own_defense": ["d_def_sacks_tr", "d_def_interceptions_tr", "d_points_against_tr"],
    "game": ["spread", "is_home"],
}
K_GROUPS = {
    "team_offense": ["d_team_epa_tr", "d_plays_tr", "d_pass_oe_tr", "d_points_for_tr"],
    "kicker_usage": ["fg_att_tr", "long_share_tr", "pat_att_tr"],
    "opp_defense": ["o_points_against_tr", "o_def_sacks_tr"],
    "game": ["spread", "is_home"],
}


def join_teams(rows: pl.DataFrame, teams: pl.DataFrame, opponent: str) -> pl.DataFrame:
    """Own and opposing trailing team features for each row (keys: team, opponent, season, week)."""
    return (
        rows.join(teams.select(*KEY, "spread", "is_home"), on=KEY, how="left")
        .join(prefixed(teams, "d_"), left_on=KEY, right_on=["d_team", "season", "week"], how="left")
        .join(
            prefixed(teams, "o_"),
            left_on=[opponent, "season", "week"],
            right_on=["o_team", "season", "week"],
            how="left",
        )
    )


def def_table(league_id: str, teams: pl.DataFrame) -> pl.DataFrame:
    points = store.read_table("defense_points").filter(
        (pl.col("league_id") == league_id) & (pl.col("season") >= streaming.SCORED_FROM)
    )
    opp = store.read_table("nfl_team_stats", "raw").select(*KEY, "opponent_team")
    rows = join_teams(points.join(opp, on=KEY), teams, "opponent_team")
    return rows.rename({"opp_implied": "implied"}).with_columns(pl.col("team").alias("unit"))


def kicker_usage() -> pl.DataFrame:
    """Per kicker-game trailing field-goal and extra-point attempts and share of kicks from 40+."""
    k = store.read_table("nfl_player_stats", "raw").filter(pl.col("position") == "K")
    long_kicks = sum(
        pl.col(c).fill_null(0)
        for c in (
            "fg_made_40_49", "fg_made_50_59", "fg_made_60_",
            "fg_missed_40_49", "fg_missed_50_59", "fg_missed_60_",
        )
    )  # fmt: skip
    k = k.with_columns(
        pl.col("fg_att").cast(pl.Float64),
        pl.col("pat_att").cast(pl.Float64),
        pl.when(pl.col("fg_att") > 0).then(long_kicks / pl.col("fg_att")).alias("long_share"),
    )
    return trailing(k, "player_id", ["fg_att", "pat_att", "long_share"]).select(
        pl.col("player_id").alias("gsis_id"),
        "season", "week", "fg_att_tr", "pat_att_tr", "long_share_tr",
    )  # fmt: skip


def k_table(league_id: str, teams: pl.DataFrame) -> pl.DataFrame:
    k = store.read_table("player_points").filter(
        (pl.col("league_id") == league_id)
        & (pl.col("position") == "K")
        & (pl.col("season") >= streaming.SCORED_FROM)
        & (pl.col("season_type") == "REG")
    )
    ecr = store.read_table("nfl_ecr", "raw").select("gsis_id", "season", "week", "ecr_pos")
    k = k.drop("is_home").join(kicker_usage(), on=["gsis_id", "season", "week"], how="left")
    k = k.join(ecr, on=["gsis_id", "season", "week"], how="left")
    rows = join_teams(k, teams, "opponent_team")
    return rows.rename({"gsis_id": "unit", "team_implied": "implied"}).with_columns(
        pl.col("roof").is_in(streaming.DOMES).cast(pl.Float64).alias("dome")
    )


def add_form(rows: pl.DataFrame) -> pl.DataFrame:
    """`form`: the unit's earlier points, shrunk toward the mean of all earlier rows."""
    return trailing(rows, "unit", ["points"]).rename({"points_tr": "form"})


def arm_prediction(fit: pl.DataFrame, games: pl.DataFrame, features: list[str]) -> np.ndarray:
    train = fit.drop_nulls(features)
    new = games.select(features).fill_null(strategy="mean").fill_null(0.0)
    return ridge_predict(
        train.select(features).to_numpy(), train["points"].to_numpy(), new.to_numpy()
    )


def walk_forward(rows: pl.DataFrame, arms: dict[str, list[str]], kind: str) -> pl.DataFrame:
    """Squared error of `current`, the league mean and every arm, one row per game and arm."""
    use_dome = kind == "K"
    base_features = ["form", "implied", *(["dome"] if use_dome else [])]
    out = []
    for (season, week), games in rows.filter(pl.col("season") >= SCORE_FROM).group_by(
        "season", "week", maintain_order=True
    ):
        earlier = (pl.col("season") < season) | (
            (pl.col("season") == season) & (pl.col("week") < week)
        )
        history = rows.filter(earlier)
        fit = history.filter(pl.col("season") >= FIT_FROM)
        if history.is_empty() or fit.height < MIN_FIT_ROWS:
            continue
        upcoming = games.select("unit", "team", "week", "implied", "roof")
        current = streaming.project_units(history, upcoming, "unit", "implied", use_dome)
        current = games.join(current.select("unit", "projection"), on="unit")
        preds = {
            "current": current["projection"].to_numpy(),
            "league_mean": np.full(games.height, float(history["points"].mean())),
        }
        for name, extra in arms.items():
            preds[name] = arm_prediction(fit, games, [*base_features, *extra])
        actual = games["points"].to_numpy()
        ranked = games["ecr_pos"].is_not_null().to_numpy() if "ecr_pos" in games.columns else None
        for name, p in preds.items():
            covered = (
                ranked if ranked is not None and "ecr" in name else np.ones(games.height, bool)
            )
            out.append(
                games.select("unit", "season", "week").with_columns(
                    arm=pl.lit(name),
                    sq=pl.Series((actual - p) ** 2),
                    ranked=pl.Series(ranked if ranked is not None else np.ones(games.height, bool)),
                    scored=pl.Series(covered),
                )
            )
    return pl.concat(out)


def paired(mine: pl.DataFrame, other: pl.DataFrame) -> tuple[float, float, float, int, int]:
    """(rmse, other rmse, weekly t of the squared-error difference, weeks, games) on shared games."""
    joined = mine.join(other, on=["unit", "season", "week"], suffix="_other")
    weekly = (
        joined.group_by("season", "week")
        .agg((pl.col("sq") - pl.col("sq_other")).mean().alias("d"))
        .sort("season", "week")["d"]
        .to_numpy()
    )
    t = float(weekly.mean() / (weekly.std(ddof=1) / np.sqrt(weekly.size)))
    rmse, rmse_other = (float(np.sqrt(joined[c].mean())) for c in ("sq", "sq_other"))
    return rmse, rmse_other, t, weekly.size, joined.height


def report(errors: pl.DataFrame, label: str) -> None:
    print(f"\n{label}")
    base = errors.filter(pl.col("arm") == "current")
    stack = errors.filter(pl.col("arm") == "stack")
    for arm in errors["arm"].unique(maintain_order=True):
        if arm == "current":
            continue
        mine = errors.filter((pl.col("arm") == arm) & pl.col("scored"))
        rmse, ref, t, weeks, games = paired(mine, base)
        line = (
            f"  {arm:14s} rmse {rmse:.3f} vs current {ref:.3f} ({100 * (rmse / ref - 1):+.2f}%) "
            f"t {t:+.2f}  games {games}"
        )
        if arm not in ("stack", "league_mean"):
            rmse, ref, t, *_ = paired(mine, stack)
            line += f" | vs stack ({100 * (rmse / ref - 1):+.2f}%) t {t:+.2f}"
        print(line)


def main() -> None:
    teams = team_features()
    for lg in store.read_table("leagues", "raw").iter_rows(named=True):
        lid = lg["league_id"]
        print(f"== {lg['league_key']} ({len(json.loads(lg['scoring_settings']))} scoring keys)")
        d_arms = {"stack": [], **{f"+{g}": c for g, c in DEF_GROUPS.items()}}
        d_arms["+all"] = [c for cols in DEF_GROUPS.values() for c in cols]
        report(walk_forward(add_form(def_table(lid, teams)), d_arms, "DEF"), "DEF")
        k_arms = {"stack": [], **{f"+{g}": c for g, c in K_GROUPS.items()}}
        k_arms["+ecr"] = ["ecr_pos"]
        k_arms["+all_k"] = [c for cols in K_GROUPS.values() for c in cols]
        report(walk_forward(add_form(k_table(lid, teams)), k_arms, "K"), "K")


if __name__ == "__main__":
    main()
