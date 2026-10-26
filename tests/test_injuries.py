import numpy as np
import polars as pl
import pytest

from fantasy import store
from fantasy.sim import odds
from fantasy.sim.blend import blend
from fantasy.sim.injuries import InjuryModel, injury_projections, without_stat_line
from fantasy.sim.value import absence_probs, conditional_values, play_curves
from fantasy.stages import injuries as stage


def _effects() -> pl.DataFrame:
    def row(status: str, practice: str, body: str, p: tuple[float, ...], perf: float) -> dict:
        return {
            "status": status,
            "practice": practice,
            "body": body,
            "n": 100,
            **{f"p{k}": p[k] for k in range(4)},
            "perf": perf,
        }

    rows = [
        row("Questionable", "any", "any", (0.7, 0.75, 0.75, 0.75), 0.95),
        row("Questionable", "any", "Hamstring", (0.55, 0.69, 0.71, 0.69), 0.9),
        row("Questionable", "any", "Other", (0.7, 0.75, 0.75, 0.75), 0.95),
        row("Questionable", "DNP", "any", (0.4, 0.6, 0.7, 0.7), 0.95),
        row("Out", "any", "any", (0.0, 0.3, 0.5, 0.6), 1.0),
    ]
    return pl.DataFrame(rows, schema=store.SCHEMAS["injury_effects"])


def test_curve_uses_the_most_specific_cell_and_falls_back() -> None:
    model = InjuryModel(_effects())
    hamstring = model.curve(("Questionable", "Hamstring", None))
    assert hamstring is not None
    assert hamstring[0][:4] == (0.55, 0.69, 0.71, 0.69) and hamstring[1] == 0.9
    assert model.curve(("Questionable", "Hamstring", "DNP"))[0][0] == 0.4  # type: ignore[index]
    assert model.curve(("Questionable", "Toe", None))[0][0] == 0.7  # type: ignore[index]
    assert model.curve(("Out", "Hamstring", None))[0][:4] == (0.0, 0.3, 0.5, 0.6)  # type: ignore[index]
    assert model.curve(("Healthy-ish", None, None)) is None
    assert model.curve(("IR", None, None))[0] == (0.0, 0.0, 0.0, 0.0, 1.0)  # type: ignore[index]


def test_projections_follow_the_players_own_games_and_leave_others_alone() -> None:
    games = [(7, 10.0), (8, 10.0), (10, 10.0), (11, 10.0), (12, 10.0)]  # week 9 is a bye
    rows = [("hurt", w, v) for w, v in games] + [("fine", w, v) for w, v in games]
    frame = pl.DataFrame(rows, schema=["gsis_id", "week", "projection"], orient="row")
    out = injury_projections(
        frame,
        {"hurt": ("Questionable", "Hamstring", None)},
        InjuryModel(_effects()),
        current_week=7,
    ).sort("gsis_id", "week")
    hurt = out.filter(pl.col("gsis_id") == "hurt")
    assert hurt["play_prob"].to_list()[:4] == [0.55, 0.69, 0.71, 0.69]  # the bye is skipped
    assert hurt["play_prob"][4] == 1.0
    # points when playing: the play-through discount (0.9) halves its pull each game
    cond = (hurt["projection"] / hurt["play_prob"]).to_list()
    assert cond[:3] == pytest.approx([9.0, 9.5, 9.75])
    assert out.filter(pl.col("gsis_id") == "fine")["play_prob"].to_list() == [1.0] * 5


def test_a_table_chance_of_playing_replaces_the_stat_line_chance() -> None:
    # the table's chance counts a game with touches or targets, which already is the stat-line
    # event, so its games get p * E, not p * q * E; the classifier's first-game chance (any
    # offensive snaps) keeps q, and so does a healthy game after the curve
    weeks = [7, 8, 9, 10, 11]
    rows = [("hurt", w, 9.0) for w in weeks] + [("snaps", w, 9.0) for w in weeks]
    frame = pl.DataFrame(
        rows + [("fine", 7, 9.0)], schema=["gsis_id", "week", "projection"], orient="row"
    )
    q = {(g, w): 0.9 for g, w, _ in rows} | {("fine", 7): 0.9}  # E is 10 everywhere
    flag = ("Questionable", "Hamstring", None)
    flags, model, first = {"hurt": flag, "snaps": flag}, InjuryModel(_effects()), {"snaps": 0.8}
    conditional = without_stat_line(frame, flags, model, 7, first, q)
    out = injury_projections(conditional, flags, model, 7, first_game_chance=first).sort(
        "gsis_id", "week"
    )
    perf = [1 - 0.1 * 0.5**k for k in range(5)]
    hurt = out.filter(pl.col("gsis_id") == "hurt")
    expected = [p * f * 10.0 for p, f in zip([0.55, 0.69, 0.71, 0.69], perf, strict=False)]
    assert hurt["projection"].to_list()[:4] == pytest.approx(expected)
    assert hurt["projection"][4] == pytest.approx(perf[4] * 9.0)
    snaps = out.filter(pl.col("gsis_id") == "snaps")
    assert snaps["projection"][0] == pytest.approx(0.8 * perf[0] * 9.0)
    assert snaps["projection"][1] == pytest.approx(0.69 * perf[1] * 10.0)
    assert out.filter(pl.col("gsis_id") == "fine")["projection"].item() == 9.0


def test_the_stat_line_chance_comes_out_of_our_projection_before_the_sleeper_blend() -> None:
    # ours is E * q = 10 * 0.8, Sleeper says 12, the table's chance is 0.55 (hamstring, game 0)
    ours = pl.DataFrame({"gsis_id": ["hurt"], "week": [7], "projection": [8.0]})
    theirs = pl.DataFrame({"gsis_id": ["hurt"], "week": [7], "other": [12.0]})
    flags, model = {"hurt": ("Questionable", "Hamstring", None)}, InjuryModel(_effects())
    conditional = without_stat_line(ours, flags, model, 7, None, {("hurt", 7): 0.8})
    blended = blend(conditional, theirs, "gsis_id")
    assert blended["projection"].item() == pytest.approx(0.5 * 10.0 + 0.5 * 12.0)
    out = injury_projections(blended, flags, model, 7)
    assert out["projection"].item() == pytest.approx(0.55 * 0.9 * 11.0)


def test_a_flagged_game_without_a_stat_line_chance_is_warned_about() -> None:
    ours = pl.DataFrame({"gsis_id": ["hurt"], "week": [7], "projection": [8.0]})
    flags, model = {"hurt": ("Questionable", "Hamstring", None)}, InjuryModel(_effects())
    with pytest.warns(UserWarning, match="no stat-line chance"):
        out = without_stat_line(ours, flags, model, 7, None, {("other", 7): 0.8})
    assert out["projection"].item() == 8.0


def test_weeks_before_the_current_one_are_untouched() -> None:
    frame = pl.DataFrame({"gsis_id": ["a", "a"], "week": [6, 7], "projection": [10.0, 10.0]})
    out = injury_projections(
        frame, {"a": ("Out", None, None)}, InjuryModel(_effects()), current_week=7
    ).sort("week")
    assert out["play_prob"].to_list() == [1.0, 0.0] and out["projection"].to_list() == [10.0, 0.0]


def test_play_curves_trim_to_the_last_week_below_one_and_the_chain_continues() -> None:
    frame = pl.DataFrame(
        {
            "gsis_id": ["a", "a", "a", "a", "b"],
            "week": [7, 8, 9, 10, 7],
            "play_prob": [0.5, 0.8, 1.0, 1.0, 1.0],
            "projection": [5.0, 8.0, 10.0, 10.0, 10.0],
        }
    )
    assert play_curves(frame, [7, 8, 9, 10]) == {"a": (0.5, 0.8)}
    assert absence_probs((0.5, 0.8), 4, 0.07, 0.55)[:2] == pytest.approx([0.5, 0.2])
    assert conditional_values(frame)[7] == {"a": 10.0, "b": 10.0}


def test_a_recovering_player_who_returns_stays_back_within_the_curve() -> None:
    path = odds.absence_path("x", (0.2, 0.5, 0.8, 1.0), 4, 5000, 0, 0.07, 0.55)
    assert not (path[1:] & ~path[:-1]).any()  # never out again after playing, within the curve
    assert path.mean(axis=1) == pytest.approx([0.8, 0.5, 0.2, 0.0], abs=0.03)


def _panel() -> pl.DataFrame:
    rows = []
    for body, share, n in (("Hamstring", 0.5, 60), ("Groin", 0.9, 60), ("Toe", 1.0, 2)):
        for i in range(n):
            plays = i < round(share * n)
            rows.append(
                {
                    "report_status": "Out",
                    "practice": None,
                    "body": body,
                    "p0": False,
                    "p1": plays,
                    "p2": plays,
                    "p3": plays,
                    "points": None,
                    "proj": None,
                }
            )
    return pl.DataFrame(rows)


def test_estimate_separates_slow_and_fast_injuries_and_shrinks_thin_cells() -> None:
    table = stage.estimate(_panel())
    out = table.filter((pl.col("status") == "Out") & (pl.col("practice") == "any"))
    cell = {r["body"]: r for r in out.iter_rows(named=True)}
    assert cell["Groin"]["p1"] > cell["any"]["p1"] > cell["Hamstring"]["p1"]
    assert (table["p0"] <= 1.0).all() and (table["p0"] >= 0.0).all()


def test_shrink_pulls_a_thin_cell_to_its_parent_and_a_thick_one_stays() -> None:
    parent = stage.Effect(500, (0.5,) * 4, 1.0)
    thin = stage.Cell(2, (2,) * 4, (1.0,) * 4, 0, 0.0, 0.0)
    thick = stage.Cell(2000, (2000,) * 4, (1.0,) * 4, 0, 0.0, 0.0)
    assert stage.shrink(thin, parent).p[0] == pytest.approx(0.5 + 0.5 * 2 / 32)
    assert stage.shrink(thick, parent).p[0] > 0.98
    assert np.isclose(stage.shrink(thin, None).p[0], 1.0)


def test_an_unknown_status_is_treated_as_questionable_with_a_warning() -> None:
    frame = pl.DataFrame(
        [("p", 7, 10.0), ("p", 8, 10.0)], schema=["gsis_id", "week", "projection"], orient="row"
    )
    with pytest.warns(UserWarning, match="Healthy-ish"):
        out = injury_projections(
            frame, {"p": ("Healthy-ish", "Hamstring", None)}, InjuryModel(_effects()), 7
        )
    assert out["play_prob"][0] == 0.55  # the Questionable hamstring curve


def test_a_status_with_no_rows_stores_no_cells_instead_of_never_plays() -> None:
    table = stage.estimate(_panel())  # the panel has only Out rows
    assert set(table["status"]) == {"Out"}


def test_a_root_cell_with_no_games_at_a_horizon_takes_the_previous_rate() -> None:
    cell = stage.Cell(10, (10, 10, 0, 0), (0.8, 0.6, 0.0, 0.0), 0, 0.0, 0.0)
    assert stage.shrink(cell, None).p == (0.8, 0.6, 0.6, 0.6)
