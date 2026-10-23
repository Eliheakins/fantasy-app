"""Load config.toml from the repo root."""

import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Config:
    season: int
    user_id: str
    n_sims: int
    leagues: dict[str, str]  # league name -> Sleeper league id


def load_config(path: Path = ROOT / "config.toml") -> Config:
    raw = tomllib.loads(path.read_text())
    try:
        return Config(
            season=raw["season"],
            user_id=raw["user_id"],
            n_sims=raw["n_sims"],
            leagues={name: league["id"] for name, league in raw["leagues"].items()},
        )
    except KeyError as missing:
        raise ValueError(f"{path} is missing {missing}") from missing
