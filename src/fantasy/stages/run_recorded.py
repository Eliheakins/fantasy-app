"""Run one refresh step and record its outcome: run_recorded <stage> <module> [args...].

Exit code is the step's own; a soft failure (see fantasy._runs) is recorded but exits 0, so
make goes on and refresh_report ends the run with the failures.
"""

import sys

from fantasy._runs import run_stage


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: run_recorded <stage> <module> [args...]", file=sys.stderr)
        return 2
    return run_stage(argv[0], argv[1], argv[2:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
