import polars as pl
import pytest

from fantasy.sim.scoring_scale import position_scale, reference_league, scale_points


def test_reference_league_is_the_same_whatever_the_table_order() -> None:
    assert reference_league(pl.DataFrame({"league_id": ["9", "2", "5"]})) == "2"
    assert reference_league(pl.DataFrame({"league_id": ["5", "9", "2"]})) == "2"


def test_a_lower_scoring_league_scales_point_effects_down_and_leaves_ratios_alone() -> None:
    baseline = pl.DataFrame(
        {
            "league_id": ["ref", "ref", "low", "low"],
            "position": ["WR", "QB", "WR", "QB"],
            "projection": [10.0, 20.0, 8.0, 20.0],
        }
    )
    scale = position_scale(baseline, "low", "ref")
    assert scale == {"WR": pytest.approx(0.8), "QB": pytest.approx(1.0)}
    effects = {("WR", "vac_target"): 3.0, ("WR", "first_back_injury"): 0.9}
    got = scale_points(effects, scale, frozenset({"vac_target"}))
    assert got[("WR", "vac_target")] == pytest.approx(2.4)
    assert got[("WR", "first_back_injury")] == 0.9


def test_a_point_effect_for_a_position_without_a_scale_raises() -> None:
    with pytest.raises(ValueError, match="TE"):
        scale_points({("TE", "vac_target"): 3.0}, {"WR": 0.8}, frozenset({"vac_target"}))
    assert scale_points({("TE", "ratio"): 0.9}, {}, frozenset({"vac_target"})) == {
        ("TE", "ratio"): 0.9
    }
