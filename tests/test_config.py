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
