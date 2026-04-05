from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

import polars as pl
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Paths & configuration
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent
_data_dir_override = os.environ.get("DATA_LOCAL_DIR", "").strip()
DATA_DIR = Path(_data_dir_override).resolve() if _data_dir_override else BACKEND_DIR / "data"
DEFAULT_PLAYER_INDEX_PATH = DATA_DIR / "player_index.parquet"

PBP_SHARD_PATTERN = re.compile(r"^nfl_pbp_(\d{4})\.parquet$")

_player_index: pl.DataFrame | None = None
_data_source: str = "local"
_pbp_shards_cached: list["PbpShard"] = []


def _parse_csv_env(name: str, default: str) -> list[str]:
    raw = os.environ.get(name, default).strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def cors_allow_origins() -> list[str]:
    """Comma-separated origins; defaults for local Vite."""
    defaults = "http://localhost:3000,http://127.0.0.1:3000"
    return _parse_csv_env("CORS_ORIGINS", defaults)


def get_player_index() -> pl.DataFrame:
    if _player_index is None:
        raise HTTPException(
            status_code=503,
            detail="Player index not loaded. Seed data (e.g. run scripts/dataPipeline.py into DATA_LOCAL_DIR) and restart the service.",
        )
    return _player_index


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class PlayerRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    gsis_id: str
    full_name: str | None = None

    @field_validator("gsis_id", mode="before")
    @classmethod
    def gsis_id_as_str(cls, v: Any) -> str:
        if v is None:
            raise ValueError("gsis_id is required")
        return str(v).strip()

    position: str | None = None
    team: str | None = None
    headshot_url: str | None = None
    birth_date: Any = None
    years_exp: int | float | None = None


class PbpShard(BaseModel):
    year: int = Field(..., description="Season year from the parquet filename")
    path: str = Field(
        ...,
        description="Relative URL under the API (/data/...) or absolute HTTPS URL (e.g. R2 public URL)",
    )


class PlayerDetailResponse(BaseModel):
    player: PlayerRecord
    shards: list[PbpShard]


class HealthResponse(BaseModel):
    status: str
    data_source: str
    player_index_loaded: bool


# ---------------------------------------------------------------------------
# Domain logic
# ---------------------------------------------------------------------------


def _normalize_gsis_id_expr(col: pl.Expr) -> pl.Expr:
    """Compare GSIS ids as strings (parquet may store Utf8 or other types)."""
    return col.cast(pl.Utf8).str.strip_chars()


def load_player_index_from_path(path: Path) -> pl.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"Player index not found: {path}")
    return pl.read_parquet(path)


def load_player_index_from_url(url: str) -> pl.DataFrame:
    return pl.read_parquet(url)


def search_players_by_name(df: pl.DataFrame, q: str, *, limit: int = 10) -> list[dict[str, Any]]:
    needle = q.strip()
    if not needle:
        return []

    filtered = df.filter(
        pl.col("full_name").str.to_lowercase().str.contains(needle.lower(), literal=True)
    ).head(limit)

    return filtered.to_dicts()


def get_player_row_as_dict(df: pl.DataFrame, gsis_id: str) -> dict[str, Any] | None:
    target = gsis_id.strip()
    if not target:
        return None

    match = df.filter(_normalize_gsis_id_expr(pl.col("gsis_id")) == target)
    if match.height == 0:
        return None
    return match.to_dicts()[0]


def discover_pbp_shards_local(data_dir: Path) -> list[PbpShard]:
    if not data_dir.is_dir():
        return []

    shards: list[PbpShard] = []
    for file_path in data_dir.iterdir():
        if not file_path.is_file():
            continue
        m = PBP_SHARD_PATTERN.match(file_path.name)
        if not m:
            continue
        year = int(m.group(1))
        path = f"/data/{file_path.name}"
        shards.append(PbpShard(year=year, path=path))

    return sorted(shards, key=lambda s: s.year)


def discover_pbp_shards_r2(public_base: str, years: list[int]) -> list[PbpShard]:
    base = public_base.rstrip("/")
    out = [PbpShard(year=y, path=f"{base}/nfl_pbp_{y}.parquet") for y in years]
    return sorted(out, key=lambda s: s.year)


def parse_pbp_years_env() -> list[int]:
    raw = os.environ.get("PBP_YEARS", "").strip()
    if not raw:
        return []
    years: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        years.append(int(part, 10))
    return years


# ---------------------------------------------------------------------------
# App factory & lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _player_index, _data_source, _pbp_shards_cached

    _data_source = os.environ.get("DATA_SOURCE", "local").strip().lower() or "local"

    if _data_source == "r2":
        index_url = os.environ.get("PLAYER_INDEX_URL", "").strip()
        if not index_url:
            raise RuntimeError("DATA_SOURCE=r2 requires PLAYER_INDEX_URL (HTTPS URL to player_index.parquet)")

        public_base = os.environ.get("PUBLIC_PBP_BASE", "").strip()
        if not public_base:
            raise RuntimeError("DATA_SOURCE=r2 requires PUBLIC_PBP_BASE (HTTPS base URL for nfl_pbp_YYYY.parquet)")

        years = parse_pbp_years_env()
        if not years:
            raise RuntimeError("DATA_SOURCE=r2 requires PBP_YEARS (comma-separated years, e.g. 2021,2022,2023,2024)")

        _player_index = load_player_index_from_url(index_url)
        _pbp_shards_cached = discover_pbp_shards_r2(public_base, years)
    elif _data_source == "local":
        index_path = Path(os.environ.get("PLAYER_INDEX_PATH", str(DEFAULT_PLAYER_INDEX_PATH)))
        if index_path.is_file():
            _player_index = load_player_index_from_path(index_path)
            _pbp_shards_cached = discover_pbp_shards_local(DATA_DIR)
        else:
            _player_index = None
            _pbp_shards_cached = []
    else:
        raise RuntimeError(f"Invalid DATA_SOURCE={_data_source!r}; use 'local' or 'r2'")

    yield


app = FastAPI(title="NFL Stat API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Range", "Content-Length", "Accept-Ranges"],
)

# URL path `/data` maps to filesystem DATA_DIR (local: backend/data; Render: DATA_LOCAL_DIR e.g. /data).
if (
    (os.environ.get("DATA_SOURCE", "local").strip().lower() or "local") == "local"
    and DATA_DIR.is_dir()
):
    app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok" if _player_index is not None else "degraded",
        data_source=_data_source,
        player_index_loaded=_player_index is not None,
    )


@app.get("/search", response_model=list[PlayerRecord])
async def search_players(
    q: Annotated[str, Query(description="Substring to match against full_name (case-insensitive)")],
    df: Annotated[pl.DataFrame, Depends(get_player_index)],
) -> list[PlayerRecord]:
    rows = search_players_by_name(df, q, limit=10)
    return [PlayerRecord.model_validate(r) for r in rows]


@app.get("/player/{gsis_id}", response_model=PlayerDetailResponse)
async def get_player(
    gsis_id: str,
    df: Annotated[pl.DataFrame, Depends(get_player_index)],
) -> PlayerDetailResponse:
    raw = get_player_row_as_dict(df, gsis_id)
    if raw is None:
        raise HTTPException(status_code=404, detail=f"Player not found for gsis_id={gsis_id!r}")

    player = PlayerRecord.model_validate(raw)
    return PlayerDetailResponse(player=player, shards=_pbp_shards_cached)
