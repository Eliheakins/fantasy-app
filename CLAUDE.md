# fantasy-app

Personal NFL fantasy decision tool (Sleeper, redraft, two leagues). Local only, $0, Python 3.12 with uv.

## Commands

- `make setup`: install dependencies and enable the git hook
- `make check`: ruff, mypy and pytest. Run before committing.
- `make fmt`: auto-fix lint and formatting

## Run it

- `make refresh`: pull Sleeper and nflverse and rebuild every table (needs the network)
- `make app`: open the dashboard
- `make odds`: archive one week of prop lines (needs `ODDS_API_KEY` in env or `.env`, gitignored; free tier is 500 credits a month, a snapshot costs about 80)
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

## How it fits together

Stages (`src/fantasy/stages/`, run by `make refresh` in this order) read and write parquet tables registered in `store.SCHEMAS`. `src/fantasy/sim/` holds the pure logic; `stages/simulate.py` builds a `LeagueData` from the tables and `data_api.py` serves it to the Streamlit pages in `app/`.

1. `sync_sleeper`, `sleeper_projections`, `ingest_nfl`, `crosswalk`: raw data and the Sleeper to nflverse ID map.
2. `score`, `streaming`: points per league's scoring; K and DEF.
3. `project`: baseline projection. `distributions`: size calibration, per-tier marginals, correlations.
4. `injuries`, `outlook`, `environment`: measured effects (tables `injury_effects`, `outlook_effects`, `environment_effects`).
5. `simulate`: applies calibration, the Sleeper blend (`sim/blend.py`), injury, outlook and environment layers, then season odds.

A missing table for a layer in step 4, or for calibration or the Sleeper blend, is skipped without error; the stale banner lists what is missing (`data_api.missing_layers`).

## Gotchas

- `data/` is gitignored. A fresh clone has no data: run `make setup`, then `make refresh` (needs the network).
- `data/archive/` cannot be regenerated: Sleeper projection snapshots (re-stamped by the endpoint after games, so only our own snapshots are clean), odds snapshots, season-odds history. Back it up before wiping `data/`. Issue #40 depends on it.
- Point-valued effects are measured in the reference league (lowest league id) and scaled per league (`sim/scoring_scale.py`). Add a new point-valued effect to the `*_POINT_KINDS` sets in `stages/simulate.py`, or YinzBurgh (0.5 PPR) will be overstated.
- My teams: Colgate "Lisan Al-Caleb", YinzBurgh "LaPorta Potty" (Sleeper's `is_me` flag, not the league's top team).
- `data_api.py` is 1150 lines. Splitting it would bypass tests that patch `data_api.leagues` and `data_api._read`; fix those patches first.

## Standard for model changes

A change to a projection or distribution ships only if it improves held-out error (fit 2019 to 2023, score 2024 on) or has a clear t-statistic (|t| of 2 or more) and the stages and tests pass. Record every test, shipped or not, with numbers in `docs/decisions.md`. Scripts behind past tests are in `research/` (see its README). Rejected ideas are listed there; read them before re-proposing one.

## Dates that matter (2026 season)

- Trade deadline: week 11. Issue #40 (retest the 50% Sleeper blend weight on clean snapshots) is due around then.
- `make odds` costs about 80 of 500 monthly credits per snapshot.
