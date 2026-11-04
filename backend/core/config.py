from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent

# Local Vite dev server origins.
CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_REPO_ROOT / ".env", extra="ignore")

    # OpenAI-compatible local server, e.g. `uv run --group llm mlx_lm.server --model <LLM_MODEL>`.
    llm_base_url: str = Field(default="http://127.0.0.1:8080/v1", validation_alias="LLM_BASE_URL")
    llm_model: str = Field(
        default="mlx-community/Qwen2.5-14B-Instruct-4bit", validation_alias="LLM_MODEL"
    )
    llm_timeout_seconds: float = Field(default=120.0, validation_alias="LLM_TIMEOUT_SECONDS")

    @property
    def backend_dir(self) -> Path:
        return _BACKEND_DIR

    @property
    def data_dir(self) -> Path:
        return _BACKEND_DIR / "data"


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
