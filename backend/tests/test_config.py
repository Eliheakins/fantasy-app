from __future__ import annotations

import pytest

from core.config import AppSettings

LLM_VARS = ("LLM_BASE_URL", "LLM_MODEL", "LLM_TIMEOUT_SECONDS")


def test_defaults_point_at_the_local_model_server_and_backend_data_folder(
    monkeypatch: pytest.MonkeyPatch,
):
    for var in LLM_VARS:
        monkeypatch.delenv(var, raising=False)

    settings = AppSettings(_env_file=None)

    assert settings.llm_base_url == "http://127.0.0.1:8080/v1"
    assert settings.llm_timeout_seconds == 120.0
    assert settings.backend_dir.name == "backend"
    assert settings.data_dir == settings.backend_dir / "data"


def test_environment_variables_override_the_model_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("LLM_MODEL", "other-model")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "5")

    settings = AppSettings(_env_file=None)

    assert settings.llm_base_url == "http://127.0.0.1:1234/v1"
    assert settings.llm_model == "other-model"
    assert settings.llm_timeout_seconds == 5.0
