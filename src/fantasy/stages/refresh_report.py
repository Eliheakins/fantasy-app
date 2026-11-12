"""End of `make refresh`: list the steps that failed or were skipped since --since; exit 1."""

import argparse
from pathlib import Path

from fantasy import _runs


def main(argv: list[str] | None = None, data_dir: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, help="ISO time this refresh started")
    since = _runs.parse_utc(parser.parse_args(argv).since)
    runs = _runs.latest_runs(data_dir).to_dicts()
    recent = [r for r in runs if _runs.parse_utc(str(r["finished_at"])) >= since]
    if not recent:  # a run that recorded nothing is not a run that went well
        print(f"REFRESH FAILED: no stage recorded since {since.isoformat()}")
        return 1
    failed = [r for r in recent if r["status"] == "failed"]
    if not failed:
        print("refresh finished: every stage ok")
        return 0
    print(f"REFRESH FAILED: {len(failed)} stage(s) failed or were skipped")
    for run in failed:
        print(f"  {run['stage']}: {run['error']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
