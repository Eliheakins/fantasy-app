import numpy as np
import polars as pl
import pytest

from fantasy import store
from fantasy.sim.environment import Situation, apply_environment, effects_dict
from fantasy.stages import environment as env


def _efficiency() -> pl.DataFrame:
    rows = []
    for week in range(1, 9):
        rows.append((2025, week, "SACK", "X", 0.1, 0.15))  # a team that is sacked a lot
        rows.append((2025, week, "FINE", "X", 0.1, 0.03))
    return pl.DataFrame(
        rows, schema=["season", "week", "team", "opponent", "pass_epa", "sack_rate"], orient="row"
    )


def test_ratings_start_neutral_and_rate_a_heavily_sacked_team_above_the_rest() -> None:
    out = env.ratings(_efficiency())
    first = out.filter((pl.col("week") == 1) & (pl.col("team") == "SACK"))
    assert first["sack_rate"][0] == 0.0 and first["sack_rate_z"][0] == 0.0
    latest = out.filter(pl.col("week") == env.LATEST)
    z = dict(zip(latest["team"], latest["sack_rate_z"], strict=True))
    assert z["SACK"] > 0 > z["FINE"]
    assert len(latest) == 2  # one latest rating per team, to carry into the coming games


def _snaps_and_injuries() -> tuple[pl.DataFrame, pl.DataFrame]:
    rows = []
    for week in range(1, 8):
        for player, snaps in (("Ann Ace", 60.0), ("Bob Bench", 55.0), ("Cal Third", 10.0)):
            rows.append(("g", 2025, week, "DEF1", player, "CB", snaps))
    snaps = pl.DataFrame(
        rows,
        schema=["game_id", "season", "week", "team", "player", "position", "defense_snaps"],
        orient="row",
    )
    injuries = pl.DataFrame(
        [
            (2025, 6, "DEF1", "Ann Ace", "Out", "Hamstring", "REG"),
            (2025, 6, "DEF1", "Cal Third", "Out", "Knee", "REG"),  # not a leading corner
            (2025, 7, "DEF1", "Bob Bench", "Questionable", "Ankle", "REG"),  # not out
        ],
        schema=[
            "season",
            "week",
            "team",
            "full_name",
            "report_status",
            "report_primary_injury",
            "game_type",
        ],
        orient="row",
    ).with_columns(pl.lit(None, pl.String).alias("practice_primary_injury"))
    return snaps, injuries


def test_cb_out_counts_only_leading_corners_listed_out_or_doubtful() -> None:
    snaps, injuries = _snaps_and_injuries()
    table = env.cb_out_table(snaps, injuries)
    counts = {r["week"]: r["cb_out"] for r in table.iter_rows(named=True)}
    assert counts[6] == 1.0  # Ann Ace is out; the third corner does not count
    assert counts[7] == 0.0  # a Questionable corner is not counted in the history
    assert min(counts) == env.MIN_GAMES_CB  # a team needs a few games before its leaders are known


def test_live_cb_absent_expects_an_out_corner_to_miss_this_game() -> None:
    snaps, injuries = _snaps_and_injuries()
    games = pl.DataFrame(
        {"team": ["DEF1"] * 3, "season": [2025] * 3, "week": [8, 9, 10], "game_type": ["REG"] * 3}
    )
    live = injuries.filter(pl.col("report_status") == "Out").with_columns(pl.lit(8).alias("week"))
    got = env.live_cb_absent(snaps, live, games, None, 2025, 8)
    assert got == {("DEF1", 8): 1.0}  # without an injury model an Out corner misses this game only


def _panel() -> pl.DataFrame:
    rng = np.random.default_rng(7)
    n = 6000
    cb = (rng.random(n) < 0.2).astype(float)
    sack = rng.standard_normal(n)
    rows = {
        "position": ["WR"] * n,
        "first_back": [0.0] * n,
        "second_back": [0.0] * n,
        "vac_target": [0.0] * n,
        "vac_carry": [0.0] * n,
        "log_context": [0.0] * n,
        "pass_epa": rng.standard_normal(n),
        "sack_rate": sack,
        "cb_out": cb,
        "miss": 1.0 * cb + 0.3 * sack + rng.standard_normal(n) * 5,
    }
    return pl.DataFrame(rows)


def test_estimate_recovers_a_corner_effect_and_finds_nothing_in_pure_noise() -> None:
    table = env.estimate(_panel())
    got = {(r["position"], r["kind"]): r for r in table.iter_rows(named=True)}
    assert got[("WR", "opp_cb_out")]["value"] == pytest.approx(1.0, abs=0.35)
    assert abs(got[("WR", "opp_cb_out")]["t"]) > 2.0
    noise = got[("WR", "team_pass_epa")]  # no effect planted
    assert abs(noise["t"]) < 3.0 and abs(noise["value"]) < 0.25
    assert got[("QB", "opp_cb_out")]["value"] == 0.0 and got[("QB", "opp_cb_out")]["n"] == 0
    store.check_schema("environment_effects", table)


def test_only_clear_effects_are_applied() -> None:
    table = pl.DataFrame(
        {
            "position": ["WR", "WR"],
            "kind": ["opp_cb_out", "team_pass_epa"],
            "value": [0.7, -0.3],
            "t": [3.0, -1.0],
            "n": [100, 100],
        }
    )
    assert effects_dict(table) == {("WR", "opp_cb_out"): 0.7}


def _projections() -> pl.DataFrame:
    return pl.DataFrame(
        [
            ("wr", 7, "WR", "A", 10.0, 1.0),
            ("wr", 8, "WR", "A", 10.0, 1.0),
            ("wr", 6, "WR", "A", 10.0, 1.0),
            ("qb", 7, "QB", "A", 20.0, 0.5),
            ("low", 7, "WR", "A", 0.2, 1.0),
        ],
        schema=["gsis_id", "week", "position", "team", "projection", "play_prob"],
        orient="row",
    )


def test_apply_adds_the_effects_scaled_by_play_chance_and_clips_at_zero() -> None:
    situation = Situation(
        {"A": (1.0, 2.0)}, {("B", 7): 1.0, ("B", 8): 0.0}, {("A", 7): "B", ("A", 8): "B"}
    )
    effects = {("WR", "opp_cb_out"): 0.7, ("WR", "team_sack_rate"): 0.2, ("QB", "opp_cb_out"): 1.0}
    out = apply_environment(_projections(), situation, effects, current_week=7)
    got = {(r["gsis_id"], r["week"]): r for r in out.iter_rows(named=True)}
    assert got[("wr", 7)]["projection"] == pytest.approx(10.0 + 0.7 + 0.2 * 2.0)
    assert got[("wr", 8)]["matchup_points"] == 0.0  # that week's corner is healthy
    assert got[("wr", 6)]["projection"] == 10.0  # past weeks untouched
    assert got[("qb", 7)]["projection"] == pytest.approx(20.0 + 0.5 * 1.0)  # scaled by play chance
    negative = {("WR", "team_sack_rate"): -1.0}
    clipped = apply_environment(_projections(), situation, negative, current_week=7)
    assert clipped.filter(pl.col("gsis_id") == "low")["projection"][0] == 0.0


def _effects(rows: list[tuple[str, str, float, float]]) -> pl.DataFrame:
    return pl.DataFrame(
        [(p, k, 100, v, t) for p, k, v, t in rows],
        schema=store.SCHEMAS["environment_effects"],
        orient="row",
    )


def test_an_effect_that_vanishes_or_flips_in_either_half_is_switched_off() -> None:
    full = _effects(
        [
            ("WR", "opp_cb_out", 0.6, 3.6),  # holds in both halves
            ("QB", "team_sack_rate", 0.4, 2.4),  # gone in the later seasons
            ("RB", "team_pass_epa", -0.3, -2.8),  # flips sign in the early seasons
        ]
    )
    early = _effects(
        [
            ("WR", "opp_cb_out", 0.6, 2.9),
            ("QB", "team_sack_rate", 0.5, 2.7),
            ("RB", "team_pass_epa", 0.1, 0.6),
        ]
    )
    late = _effects(
        [
            ("WR", "opp_cb_out", 0.7, 2.2),
            ("QB", "team_sack_rate", 0.0, 0.1),
            ("RB", "team_pass_epa", -0.4, -2.4),
        ]
    )
    out = env.replicated(full, early, late)
    t = dict(zip(out["kind"], out["t"], strict=True))
    assert t["opp_cb_out"] == 3.6 and t["team_sack_rate"] == 0.0 and t["team_pass_epa"] == 0.0
    assert set(out.columns) == set(full.columns)
