"""
Backward-compatible alias for the unified data build.

Prefer: ``python scripts/build_data.py`` (same options and defaults).
"""

from __future__ import annotations

import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from pipeline.cli import DEFAULT_YEARS, data_output_dir, run_build

DATA_DIR = data_output_dir()
YEARS = list(DEFAULT_YEARS)


def main() -> None:
    run_build(
        DATA_DIR,
        YEARS,
        build_nfl=True,
        build_cfb=True,
        build_player_index=True,
        build_rosetta=True,
    )


if __name__ == "__main__":
    main()
