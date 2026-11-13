"""Load config.toml from the repo root."""

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from nfl_stat.core.config import REPO_ROOT
from nfl_stat.core.seasons import current_season

ROOT = REPO_ROOT
PROJECTION_MODELS = ("learned", "baseline")
# sites whose terms do not forbid scraping and storage; see stages/outside_projections
OUTSIDE_SOURCES = ("fftoday",)
# sources simulate averages with ours for the current week (Sleeper also for the next three)
BLEND_SOURCES = ("sleeper", "fftoday", "props")
SKILL_POSITIONS = ("QB", "RB", "WR", "TE")
REGULAR_SEASON_WEEKS = 18  # the NFL regular season; the fantasy season ends earlier


@dataclass(frozen=True)
class Config:
    season: int
    user_id: str
    n_sims: int
    leagues: dict[str, str]  # league name -> Sleeper league id
    projection_model: str = "baseline"  # "learned" or "baseline"; learned falls back if missing
    stat_line_model: bool = False  # learned projection times P(stat line | active)
    outside_sources: tuple[str, ...] = ()  # archived by outside_projections; empty disables
    blend_sources: tuple[str, ...] = ("sleeper",)  # empty: ours only
    prop_positions: tuple[str, ...] = ("RB", "WR")  # positions that get prop-implied points


def _switch(raw: dict[str, Any], key: str, path: Path, default: bool = False) -> bool:
    """An on/off setting, `default` when absent; anything but true or false (say "false") raises."""
    value = raw.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{path}: {key} must be true or false, not {value!r}")
    return value


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
    n_sims = raw.get("n_sims")
    not_a_count = isinstance(n_sims, bool) or not isinstance(n_sims, int) or n_sims < 1
    if n_sims is not None and not_a_count:
        raise ValueError(f"{path}: n_sims must be a whole number of at least 1, not {n_sims!r}")
    try:
        raw["season"]  # a missing season stays an error here; only stat-only use may fall back
        return Config(
            season=current_season(path),
            user_id=raw["user_id"],
            n_sims=raw["n_sims"],
            leagues={name: league["id"] for name, league in raw["leagues"].items()},
            projection_model=model,
            stat_line_model=_switch(raw, "stat_line_model", path),
            outside_sources=outside,
            blend_sources=sources,
            prop_positions=positions,
        )
    except KeyError as missing:
        raise ValueError(f"{path} is missing {missing}") from missing
