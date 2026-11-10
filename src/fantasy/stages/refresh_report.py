"""End of `make refresh`: list the steps that failed or were skipped since --since; exit 1."""

import argparse
from datetime import UTC, datetime
from pathlib import Path

from fantasy import _runs


def _parse(stamp: str) -> datetime:
    parsed = datetime.fromisoformat(stamp)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def main(argv: list[str] | None = None, data_dir: Path | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, help="ISO time this refresh started")
    since = _parse(parser.parse_args(argv).since)
    runs = _runs.latest_runs(data_dir).to_dicts()
    failed = [r for r in runs if r["status"] == "failed" and _parse(str(r["finished_at"])) >= since]
    if not failed:
        print("refresh finished: every stage ok")
        return 0
    print(f"REFRESH FAILED: {len(failed)} stage(s) failed or were skipped")
    for run in failed:
        print(f"  {run['stage']}: {run['error']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
