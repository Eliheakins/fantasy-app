"""Load config.toml from the repo root."""

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECTION_MODELS = ("learned", "baseline")


@dataclass(frozen=True)
class Config:
    season: int
    user_id: str
    n_sims: int
    leagues: dict[str, str]  # league name -> Sleeper league id
    projection_model: str = "baseline"  # "learned" or "baseline"; learned falls back if missing
    environment_layer: bool = True  # opposing-corner and offense-efficiency adjustments
    stat_line_model: bool = False  # learned projection times P(stat line | active)


def load_config(path: Path = ROOT / "config.toml") -> Config:
    """Parsed config, cached per file and modification time so an edit is still picked up."""
    return _load(path, path.stat().st_mtime_ns)


@lru_cache(maxsize=16)
def _load(path: Path, _mtime_ns: int) -> Config:
    raw = tomllib.loads(path.read_text())
    model = raw.get("projection_model", "baseline")
    if model not in PROJECTION_MODELS:
        raise ValueError(
            f"{path}: projection_model must be one of {PROJECTION_MODELS}, not {model!r}"
        )
    try:
        return Config(
            season=raw["season"],
            user_id=raw["user_id"],
            n_sims=raw["n_sims"],
            leagues={name: league["id"] for name, league in raw["leagues"].items()},
            projection_model=model,
            environment_layer=bool(raw.get("environment_layer", True)),
            stat_line_model=bool(raw.get("stat_line_model", False)),
        )
    except KeyError as missing:
        raise ValueError(f"{path} is missing {missing}") from missing
