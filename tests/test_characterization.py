"""Seeded outputs of build_inputs and find_trades on the toy league, pinned before refactors."""

import pytest
from test_moves import league_with
from test_odds import toy_league

from fantasy.sim import moves, odds


@pytest.mark.parametrize("reoptimize", [False, True])
def test_build_inputs_is_pinned(reoptimize: bool) -> None:
    inputs = odds.build_inputs(toy_league(), None, 300, 3, reoptimize)
    assert inputs.mean.sum() == pytest.approx(7840.0)
    assert inputs.noise_sd.sum() == pytest.approx(1955.9100183801913)
    assert inputs.shift.sum() == pytest.approx(-215442.75069790968)
    assert (inputs.shift**2).sum() == pytest.approx(5198373.253746299)


def test_find_trades_is_pinned() -> None:
    data = league_with([("fa_wr", "WR", 15.0), ("fa_rb", "RB", 12.0), ("fa_te", "TE", 6.0)])
    rows = moves.find_trades(data, 1, n_sims=500).to_dicts()
    assert [(r["partner_id"], r["give_ids"], r["get_ids"]) for r in rows] == [
        (3, ["t1_rb1"], ["t3_rb2"]),
        (8, ["t1_rb1"], ["t8_rb2"]),
        (2, ["t1_rb1"], ["t2_rb2"]),
        (2, ["t1_wr1"], ["t2_wr1"]),
    ]
    assert rows[0]["my_title"] == pytest.approx(0.022)
    assert rows[3]["their_title"] == pytest.approx(0.018)
