"""Load config.toml from the repo root."""

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECTION_MODELS = ("learned", "baseline")
# sites whose terms do not forbid scraping and storage; see stages/outside_projections
OUTSIDE_SOURCES = ("fftoday",)
# sources simulate averages with ours for the current week (Sleeper also for the next three)
BLEND_SOURCES = ("sleeper", "fftoday", "props")
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")


@dataclass(frozen=True)
class Config:
    season: int
    user_id: str
    n_sims: int
    leagues: dict[str, str]  # league name -> Sleeper league id
    projection_model: str = "baseline"  # "learned" or "baseline"; learned falls back if missing
    environment_layer: bool = True  # opposing-corner and offense-efficiency adjustments
    outside_sources: tuple[str, ...] = ()  # archived by outside_projections; empty disables
    blend_sources: tuple[str, ...] = ("sleeper",)  # empty: ours only
    prop_positions: tuple[str, ...] = ("RB", "WR")  # positions that get prop-implied points


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
    outside = tuple(raw.get("outside_sources", ()))
    if not set(outside) <= set(OUTSIDE_SOURCES):
        raise ValueError(f"{path}: outside_sources must be among {OUTSIDE_SOURCES}, not {outside}")
    sources = tuple(raw.get("blend_sources", ("sleeper",)))
    if not set(sources) <= set(BLEND_SOURCES):
        raise ValueError(f"{path}: blend_sources must be among {BLEND_SOURCES}, not {sources}")
    positions = tuple(raw.get("prop_positions", ("RB", "WR")))
    if not set(positions) <= set(SKILL_POSITIONS):
        raise ValueError(f"{path}: prop_positions must be among {SKILL_POSITIONS}, not {positions}")
    try:
        return Config(
            season=raw["season"],
            user_id=raw["user_id"],
            n_sims=raw["n_sims"],
            leagues={name: league["id"] for name, league in raw["leagues"].items()},
            projection_model=model,
            environment_layer=bool(raw.get("environment_layer", True)),
            outside_sources=outside,
            blend_sources=sources,
            prop_positions=positions,
        )
    except KeyError as missing:
        raise ValueError(f"{path} is missing {missing}") from missing
