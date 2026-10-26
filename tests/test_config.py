from pathlib import Path

import pytest

from fantasy.config import load_config


def test_config_has_both_leagues() -> None:
    cfg = load_config()
    assert set(cfg.leagues) == {"colgate", "yinzburgh"}
    assert cfg.season == 2026


def test_missing_key_raises_clear_error(tmp_path: Path) -> None:
    bad = tmp_path / "config.toml"
    bad.write_text("season = 2026\n")
    with pytest.raises(ValueError, match="missing"):
        load_config(bad)


def test_an_edited_config_is_reloaded(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "config.toml"
    body = 'season = 2026\nuser_id = "u"\nn_sims = {n}\n[leagues.a]\nid = "1"\n'
    path.write_text(body.format(n=10))
    assert load_config(path).n_sims == 10
    path.write_text(body.format(n=2000))
    assert load_config(path).n_sims == 2000


def test_inactive_swap_and_ir_curve_are_off_unless_set(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    body = 'season = 2026\nuser_id = "u"\nn_sims = 10\n{extra}[leagues.a]\nid = "1"\n'
    path.write_text(body.format(extra=""))
    off = load_config(path)
    assert not off.inactive_swap and not off.ir_return_curve
    path.write_text(body.format(extra="inactive_swap = true\nir_return_curve = true\n"))
    on = load_config(path)
    assert on.inactive_swap and on.ir_return_curve


@pytest.mark.parametrize("key", ["inactive_swap", "ir_return_curve"])
def test_a_switch_that_is_not_true_or_false_is_rejected(tmp_path: Path, key: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        f'season = 2026\nuser_id = "u"\nn_sims = 10\n{key} = "false"\n[leagues.a]\nid = "1"\n'
    )
    with pytest.raises(ValueError, match=key):
        load_config(path)
