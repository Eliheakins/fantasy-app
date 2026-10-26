"""Do the lagged expected-touchdown features already carry goal-line usage?

(a) the production model; (b) without every rush_td_exp_* and rec_td_exp_* feature; (c) (b) plus
the red-zone and goal-line shares of pbp_features_check; (d) (a) plus those shares. Same rows and
walk-forward as pbp_features_check (2024 to 2026, both leagues). If (c) recovers what (b) loses,
the shares are redundant with expected touchdowns. Also: Spearman of the lagged goal-line carry
share with rush_td_exp_hl4 per RB-game, and RB goal-line carries per team-game.

Run from the repo root: OMP_NUM_THREADS=3 uv run python research/td_redundancy_check.py
"""

import polars as pl
from pbp_features_check import (
    KEYS,
    league_histories,
    pbp,
    redzone_table,
    score,
    scored_rows,
    walk,
)

from fantasy import store
from fantasy.stages import learn

TD_FEATURES = tuple(f for f in learn.STATE_FEATURES if f.startswith(("rush_td_exp", "rec_td_exp")))
SHARES = ["car20_share", "tgt20_share", "car5_share", "tgt5_share"]


def goal_line_counts(plays: pl.DataFrame) -> None:
    pos = (
        store.read_table("nfl_ff_opportunity", "raw")
        .select(pl.col("player_id").alias("gsis_id"), "position")
        .unique("gsis_id", keep="last")
    )
    car = plays.filter(
        (pl.col("rush_attempt") == 1)
        & pl.col("rusher_player_id").is_not_null()
        & (pl.col("yardline_100") <= 5)
    ).join(pos, left_on="rusher_player_id", right_on="gsis_id", how="left")
    team_games = plays.select("posteam", "season", "week").unique().height
    rb = car.filter(pl.col("position") == "RB")
    per_rb = rb.group_by("rusher_player_id", "posteam", "season", "week").len()
    print(
        f"goal-line carries (inside the 5) per team-game: all {car.height / team_games:.2f}, "
        f"by RBs {rb.height / team_games:.2f} ({rb.height / car.height:.0%} of them); "
        f"per RB-game with at least one: {per_rb['len'].mean():.2f}"
    )


def main() -> None:
    plays = pbp()
    goal_line_counts(plays)
    rz = redzone_table(plays)
    histories = league_histories()
    scored = scored_rows()
    cols = [f"rz_{c}" for c in SHARES]
    for i, (lid, history) in enumerate(histories.items()):
        frame = learn.lag_asof(history, rz, "gsis_id", SHARES, "rz")
        if i == 0:  # the features do not depend on league scoring
            rb = frame.filter(
                (pl.col("position") == "RB")
                & pl.col("rz_car5_share").is_not_null()
                & pl.col("rush_td_exp_hl4").is_not_null()
            )
            rho = rb.select(pl.corr("rz_car5_share", "rush_td_exp_hl4", method="spearman")).item()
            print(f"Spearman goal-line carry share (hl4) vs rush_td_exp_hl4, {rb.height} RB-games: {rho:.3f}")
        preds = {
            "a": walk(frame, []),
            "b": walk(frame, [], drop=TD_FEATURES),
            "c": walk(frame, cols, drop=TD_FEATURES),
            "d": walk(frame, cols),
        }
        rows = scored.filter(pl.col("league_id") == lid).join(
            frame.select(*KEYS, "position", "points"), on=KEYS
        )
        for name, p in preds.items():
            rows = rows.join(p.rename({"pred": name}), on=KEYS)
        out = [
            {"model": m, "vs": v, **score(rows, m, v)}
            for m, v in (("b", "a"), ("c", "a"), ("d", "a"), ("c", "b"))
        ]
        print(f"league {lid}: RMSE (a) {score(rows, 'a', 'a')['rmse']}")
        with pl.Config(tbl_cols=25, tbl_width_chars=250):
            print(pl.DataFrame(out))


if __name__ == "__main__":
    main()
