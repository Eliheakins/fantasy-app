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
