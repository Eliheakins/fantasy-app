from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
load_dotenv(_REPO_ROOT / ".env")


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    data_local_dir: str = Field(default="", validation_alias="DATA_LOCAL_DIR")
    data_source: str = Field(default="local", validation_alias="DATA_SOURCE")
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        validation_alias="CORS_ORIGINS",
    )
    player_index_url: str = Field(default="", validation_alias="PLAYER_INDEX_URL")
    player_index_path: str = Field(default="", validation_alias="PLAYER_INDEX_PATH")
    public_pbp_base: str = Field(default="", validation_alias="PUBLIC_PBP_BASE")
    public_cfb_pbp_base: str = Field(default="", validation_alias="PUBLIC_CFB_PBP_BASE")
    pbp_years: str = Field(default="", validation_alias="PBP_YEARS")
    cfb_pbp_years: str = Field(default="", validation_alias="CFB_PBP_YEARS")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL")
    openai_timeout_seconds: float = Field(default=60.0, validation_alias="OPENAI_TIMEOUT_SECONDS")

    @property
    def backend_dir(self) -> Path:
        return _BACKEND_DIR

    @property
    def data_dir(self) -> Path:
        raw = self.data_local_dir.strip()
        return Path(raw).resolve() if raw else _BACKEND_DIR / "data"

    @property
    def default_player_index_path(self) -> Path:
        return self.data_dir / "player_index.parquet"

    def cors_allow_origins_list(self) -> list[str]:
        raw = self.cors_origins.strip()
        if not raw:
            return []
        return [x.strip() for x in raw.split(",") if x.strip()]


@lru_cache
def get_settings() -> AppSettings:
    return AppSettings()
