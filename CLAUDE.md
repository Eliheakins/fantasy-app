# fantasy-app

Personal NFL fantasy decision tool (Sleeper, redraft, two leagues). Local only, $0, Python 3.12 with uv.

## Commands

- `make setup`: install dependencies and enable the git hook
- `make check`: ruff, mypy and pytest. Run before committing.
- `make fmt`: auto-fix lint and formatting

## Run it

- `make refresh`: pull Sleeper and nflverse and rebuild every table (needs the network)
- `make app`: open the dashboard
- Checks against real data: `uv run python -m fantasy.stages.validate_scoring`, `validate_standings`, `backtest`, `calibration`
- Never pipe `make check` into `tail` before committing: the pipe hides a failing exit code

## Where things are

- Plan: `docs/one-pager.md`. Backlog: `docs/backlog.md` (canonical story IDs). Decisions log: `docs/decisions.md`.
- Log every decision in `docs/decisions.md` as it is made.

## Conventions

- Parquet under `data/` (gitignored) is the source of truth. DuckDB is only in-memory views.
- The dashboard imports only `fantasy.data_api`.
- No secrets in the repo. API keys come from environment variables.
- Lean MVP: simplest method that works, tests only for math and config, no CI.
- Sleeper's API is read-only. Stay under 1,000 calls a minute and fetch the players file at most once a day.
- Annotate function signatures. Prefer frozen dataclasses.
