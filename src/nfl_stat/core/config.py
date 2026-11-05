from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Paths assume a source checkout (src/nfl_stat/core/config.py), not an installed wheel.
REPO_ROOT = Path(__file__).resolve().parents[3]

# nflverse shards only. Never league or nfl_ecr data: this folder is served over HTTP.
DEFAULT_DATA_DIR = REPO_ROOT / "data" / "stat"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    # OpenAI-compatible local server, e.g. `uv run --group llm mlx_lm.server --model <LLM_MODEL>`.
    llm_base_url: str = Field(default="http://127.0.0.1:8080/v1", validation_alias="LLM_BASE_URL")
    llm_model: str = Field(
        default="mlx-community/Qwen3-4B-Instruct-2507-4bit", validation_alias="LLM_MODEL"
    )
    llm_timeout_seconds: float = Field(default=120.0, validation_alias="LLM_TIMEOUT_SECONDS")

    # Ask's model step: Jev (TypeSafe's hosted model) or the local server above. auto means Jev
    # when JEV_API_KEY is set. A Jev failure falls back to the local server.
    intent_provider: Literal["auto", "jev", "local"] = Field(
        default="auto", validation_alias="INTENT_PROVIDER"
    )
    jev_api_key: SecretStr | None = Field(default=None, validation_alias="JEV_API_KEY")
    jev_model: str = Field(default="jev-latest", validation_alias="JEV_MODEL")
    jev_timeout_seconds: float = Field(default=10.0, gt=0, validation_alias="JEV_TIMEOUT_SECONDS")

    @property
    def data_dir(self) -> Path:
        return DEFAULT_DATA_DIR


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
