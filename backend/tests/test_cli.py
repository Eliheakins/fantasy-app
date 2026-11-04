from __future__ import annotations

from pathlib import Path

import pytest

from pipeline import cli


def test_default_years_run_from_the_first_season_to_the_current_one(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(cli, "get_current_season", lambda: 2026)

    assert cli.default_years() == [2021, 2022, 2023, 2024, 2025, 2026]


def test_default_years_never_goes_below_the_first_season(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(cli, "get_current_season", lambda: 2019)

    assert cli.default_years() == [2021]


def test_parse_years_accepts_spaces_and_trailing_commas():
    assert cli._parse_years("2022, 2023,") == [2022, 2023]


def test_parse_years_rejects_an_empty_list():
    with pytest.raises(ValueError, match="No years parsed"):
        cli._parse_years(" , ")


def test_main_builds_the_derived_years_when_none_are_given(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    calls: list[tuple[Path, list[int]]] = []
    monkeypatch.setattr(cli, "get_current_season", lambda: 2022)
    monkeypatch.setattr(cli, "run_build", lambda data_dir, years: calls.append((data_dir, years)))

    assert cli.main(["--data-dir", str(tmp_path)]) == 0

    assert calls == [(tmp_path.resolve(), [2021, 2022])]


def test_main_uses_the_years_it_is_given(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    calls: list[list[int]] = []
    monkeypatch.setattr(cli, "run_build", lambda data_dir, years: calls.append(years))

    cli.main(["--data-dir", str(tmp_path), "--years", "2023,2024"])

    assert calls == [[2023, 2024]]


def test_refresh_rebuilds_only_the_current_season(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    calls: list[list[int]] = []
    monkeypatch.setattr(cli, "get_current_season", lambda: 2026)
    monkeypatch.setattr(cli, "run_build", lambda data_dir, years: calls.append(years))

    assert cli.main(["--data-dir", str(tmp_path), "--refresh"]) == 0

    assert calls == [[2026]]


def test_refresh_cannot_be_combined_with_years(tmp_path: Path):
    with pytest.raises(SystemExit):
        cli.main(["--data-dir", str(tmp_path), "--refresh", "--years", "2024"])
