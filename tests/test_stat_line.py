from pathlib import Path

import numpy as np
import polars as pl
import pytest

from fantasy.config import load_config
from fantasy.stages import stat_line

KEY_SCHEMA = {"gsis_id": pl.String, "season": pl.Int64, "week": pl.Int64}


def active(
    statlines: list[float], weeks: list[int] | None = None, player: str = "A", season: int = 2025
) -> pl.DataFrame:
    weeks = weeks or list(range(1, len(statlines) + 1))
    rows = [(player, season, w, "WR", s) for w, s in zip(weeks, statlines, strict=True)]
    schema = KEY_SCHEMA | {"position": pl.String, "statline": pl.Float64}
    return pl.DataFrame(rows, schema=schema, orient="row")


def usage(
    snaps: list[float], weeks: list[int] | None = None, player: str = "A", season: int = 2025
) -> pl.DataFrame:
    weeks = weeks or list(range(1, len(snaps) + 1))
    rows = [(player, season, w, s, 0.1, 0.2, 5.0, 1.0) for w, s in zip(weeks, snaps, strict=True)]
    columns = {
        "snap": pl.Float64,
        "st": pl.Float64,
        "tshare": pl.Float64,
        "tgt": pl.Float64,
        "car": pl.Float64,
    }
    return pl.DataFrame(rows, schema=KEY_SCHEMA | columns, orient="row")


def no_depth() -> pl.DataFrame:
    return pl.DataFrame(schema=KEY_SCHEMA | {"depth_rank": pl.Int64})


def target(week: int, player: str = "A", season: int = 2025) -> pl.DataFrame:
    return pl.DataFrame(
        [(player, season, week, "WR")], schema=KEY_SCHEMA | {"position": pl.String}, orient="row"
    )


def test_a_games_features_ignore_that_game_and_later_ones() -> None:
    a = stat_line.history_table(active([1, 1, 0, 1, 1]), usage([0.7, 0.6, 0.1, 0.8, 0.9]))
    b = stat_line.history_table(active([1, 1, 0, 0, 0]), usage([0.7, 0.6, 0.1, 0.0, 0.0]))
    fa = stat_line.features(target(4), a, no_depth())
    fb = stat_line.features(target(4), b, no_depth())
    assert fa.select(stat_line.FEATURES).equals(fb.select(stat_line.FEATURES))
    row = fa.row(0, named=True)
    expected = pl.Series([1.0, 1.0, 0.0]).ewm_mean(half_life=4.0)[-1]
    assert row["h_statline"] == pytest.approx(expected)
    assert (row["n_prior"], row["snap_last"], row["weeks_since"]) == (3.0, 0.1, 0.0)


def test_weeks_since_counts_the_weeks_missed_before_the_game() -> None:
    hist = stat_line.history_table(active([1, 1, 1], [1, 2, 5]), usage([0.5, 0.5, 0.5], [1, 2, 5]))
    assert stat_line.features(target(5), hist, no_depth())["weeks_since"].item() == 2.0


def test_a_player_with_no_earlier_game_has_no_lagged_values() -> None:
    hist = stat_line.history_table(active([1]), usage([0.5]))
    row = stat_line.features(target(1), hist, no_depth()).row(0, named=True)
    assert row["n_prior"] == 0.0 and row["h_snap"] is None and row["weeks_since"] is None


def test_each_season_is_scored_by_a_model_fit_on_earlier_seasons(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    frames = [
        active([1, 0, 1], season=s).with_columns(
            pl.lit(None, pl.Float64).alias(c) for c in stat_line.FEATURES
        )
        for s in range(2019, 2024)
    ]
    monkeypatch.setattr(
        stat_line,
        "fit_predict",
        lambda train, test: np.full(test.height, float(train["season"].max())),
    )
    out = stat_line.history_chance(pl.concat(frames))
    later = out.filter(pl.col("season") >= 2021)
    assert later.height == 9
    assert (later["q"] == (later["season"] - 1).cast(pl.Float64)).all()


def test_every_future_game_gets_the_chance_of_the_players_next_game(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        stat_line, "fit_predict", lambda train, test: test["week"].cast(pl.Float64).to_numpy()
    )
    hist = stat_line.history_table(
        pl.concat([active([1, 1]), active([1, 1], player="B")]),
        pl.concat([usage([0.5, 0.5]), usage([0.5, 0.5], player="B")]),
    )
    future = pl.concat([target(8), target(9), target(9, "B"), target(10, "B")])
    feats = stat_line.features(target(2), hist, no_depth()).with_columns(statline=pl.lit(1.0))
    out = stat_line.next_game_chance(feats, hist, no_depth(), future, current_week=8)
    assert dict(out.sort("gsis_id").iter_rows()) == {"A": 8.0, "B": 9.0}


def test_a_player_off_this_week_uses_his_latest_depth_chart() -> None:
    hist = stat_line.history_table(active([1, 1]), usage([0.5, 0.5]))
    depth = pl.DataFrame(
        [("A", 2025, 2, 2), ("B", 2025, 2, 1)],
        schema=KEY_SCHEMA | {"depth_rank": pl.Int64},
        orient="row",
    )
    future = pl.concat([target(4), target(3, "B")])
    out = stat_line.next_game_features(future, hist, depth, current_week=3)
    ranks = dict(out.select("gsis_id", "depth_rank").sort("gsis_id").iter_rows())
    assert ranks == {"A": 2, "B": None}  # B plays this week and is not on its chart


def test_scale_multiplies_the_projection_and_fails_on_a_missing_chance() -> None:
    frame = pl.DataFrame({"gsis_id": ["A", "B"], "projection": [10.0, 4.0]})
    chance = pl.DataFrame({"gsis_id": ["A", "B"], "q": [0.9, 0.5]})
    assert stat_line.scale(frame, chance, ["gsis_id"])["projection"].to_list() == [9.0, 2.0]
    with pytest.raises(ValueError, match="no stat-line chance"):
        stat_line.scale(frame, chance.head(1), ["gsis_id"])


def test_the_stat_line_switch_defaults_off(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    body = 'season = 2026\nuser_id = "u"\nn_sims = 10\n[leagues.a]\nid = "1"\n'
    path.write_text(body)
    assert load_config(path).stat_line_model is False
    path.write_text("stat_line_model = true\n" + body)
    assert load_config(path).stat_line_model is True
