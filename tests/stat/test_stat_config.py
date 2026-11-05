from __future__ import annotations

import pytest

from nfl_stat.core.config import AppSettings

LLM_VARS = ("LLM_BASE_URL", "LLM_MODEL", "LLM_TIMEOUT_SECONDS")


def test_defaults_point_at_the_local_model_server_and_fantasy_data_stat_folder(
    monkeypatch: pytest.MonkeyPatch,
):
    for var in LLM_VARS:
        monkeypatch.delenv(var, raising=False)

    settings = AppSettings(_env_file=None)

    assert settings.llm_base_url == "http://127.0.0.1:8080/v1"
    assert settings.llm_timeout_seconds == 120.0
    assert settings.data_dir.parts[-2:] == ("data", "stat")
    assert (settings.data_dir.parents[1] / "pyproject.toml").is_file()


def test_environment_variables_override_the_model_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("LLM_MODEL", "other-model")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "5")

    settings = AppSettings(_env_file=None)

    assert settings.llm_base_url == "http://127.0.0.1:1234/v1"
    assert settings.llm_model == "other-model"
    assert settings.llm_timeout_seconds == 5.0


def test_intent_provider_defaults_to_auto_with_no_jev_key(monkeypatch: pytest.MonkeyPatch):
    for var in ("INTENT_PROVIDER", "JEV_API_KEY", "JEV_MODEL"):
        monkeypatch.delenv(var, raising=False)

    settings = AppSettings(_env_file=None)

    assert settings.intent_provider == "auto"
    assert settings.jev_api_key is None
    assert settings.jev_model == "jev-latest"


def test_the_jev_key_is_read_but_never_shown_and_a_bad_provider_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("JEV_API_KEY", "sk-secret-value")
    monkeypatch.setenv("INTENT_PROVIDER", "jev")

    settings = AppSettings(_env_file=None)

    assert settings.jev_api_key is not None
    assert settings.jev_api_key.get_secret_value() == "sk-secret-value"
    assert "sk-secret-value" not in repr(settings)
    monkeypatch.setenv("INTENT_PROVIDER", "cloud")
    with pytest.raises(ValueError):
        AppSettings(_env_file=None)
