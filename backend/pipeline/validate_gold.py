#!/usr/bin/env python3
"""
Post-build checks for gold_unified_performance.parquet (id coalesce / LEFT JOIN behavior).

Run from repo root after Rosetta:
  python backend/scripts/build_data.py --rosetta-only
  python -c "import sys; sys.path.insert(0,'backend'); from pipeline.validate_gold import main; main()"

Or from backend with PYTHONPATH=.:
  python -m pipeline.validate_gold
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import polars as pl


def _data_dir() -> Path:
    override = os.environ.get("DATA_LOCAL_DIR", "").strip()
    backend = Path(__file__).resolve().parent.parent
    return Path(override).resolve() if override else backend / "data"


def main() -> int:
    data_dir = _data_dir()
    gold_path = data_dir / "gold_unified_performance.parquet"
    if not gold_path.is_file():
        print(f"Missing {gold_path}", file=sys.stderr)
        return 1

    df = pl.read_parquet(gold_path)
    need = {"nfl_id", "cfb_id", "level", "bridge_id", "season"}
    if not need.issubset(set(df.columns)):
        print(f"Unexpected gold columns: have {df.columns}", file=sys.stderr)
        return 1

    nfl = df.filter(pl.col("level") == "NFL")
    cfb = df.filter(pl.col("level") == "CFB")

    nfl_null_nfl_id = nfl.filter(pl.col("nfl_id").is_null()).height
    cfb_null_cfb_id = cfb.filter(pl.col("cfb_id").is_null()).height

    print(f"gold rows: {df.height} (NFL {nfl.height}, CFB {cfb.height})")
    print(f"NFL rows with null nfl_id: {nfl_null_nfl_id} (expect 0 — coalesce from silver player_id)")
    print(f"CFB rows with null cfb_id: {cfb_null_cfb_id} (expect 0 — coalesce from silver player_id)")

    if nfl_null_nfl_id or cfb_null_cfb_id:
        return 2
    print("validate_gold: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
