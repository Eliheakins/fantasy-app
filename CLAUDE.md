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

- Parquet under `data/` (gitignored) is the source of truth. Stages and `data_api.py` read it with polars; DuckDB is not a dependency (add it back only if a query needs it).
- The dashboard imports only `fantasy.data_api`.
- No secrets in the repo. API keys come from environment variables.
- Lean MVP: simplest method that works, tests only for math and config, no CI.
- Sleeper's API is read-only. Stay under 1,000 calls a minute and fetch the players file at most once a day.
- Annotate function signatures. Prefer frozen dataclasses.

## How it fits together

Stages (`src/fantasy/stages/`, run by `make refresh` in this order) read and write parquet tables registered in `store.SCHEMAS`. `src/fantasy/sim/` holds the pure logic; `stages/simulate.py` builds a `LeagueData` from the tables and `data_api.py` serves it to the Streamlit pages in `app/`.

1. `sync_sleeper`, `sleeper_projections`, `ingest_nfl`, `crosswalk`: raw data and the Sleeper to nflverse ID map.
2. `score`, `streaming`: points per league's scoring; K and DEF.
3. `project`: rolling baseline (`proj_baseline`). `learn`: gradient-boosted model on lagged stats plus role data (`proj_learned`, same schema; `projection_model` in `config.toml` picks which one every later stage reads, through `store.projection_table()`). `availability`: chance of playing this week (`availability`). `distributions`: size calibration, per-tier marginals and spreads, correlations, fit on the chosen projections.
4. `injuries`, `outlook`, `environment`: measured effects (tables `injury_effects`, `outlook_effects`, `environment_effects`).
5. `simulate`: applies calibration, the Sleeper blend (`sim/blend.py`), injury (with the availability model for a flagged player's next game), outlook and, if `environment_layer` is on, environment layers, then season odds.

A missing table for a layer in step 4, or for calibration or the Sleeper blend, is skipped without error; the stale banner lists what is missing (`data_api.missing_layers`).

## Gotchas

- `data/` is gitignored. A fresh clone has no data: run `make setup`, then `make refresh` (needs the network).
- `data/archive/` cannot be regenerated: our own weekly projections for the next game (`proj_snapshots`, the clean test of the learned model), Sleeper projection snapshots (re-stamped by the endpoint after games, so only our own snapshots are clean), odds snapshots, season-odds history. Back it up before wiping `data/`. Issue #40 depends on it.
- Point-valued effects are measured in the reference league (lowest league id) and scaled per league (`sim/scoring_scale.py`). Add a new point-valued effect to the `*_POINT_KINDS` sets in `stages/simulate.py`, or YinzBurgh (0.5 PPR) will be overstated.
- My teams: Colgate "Lisan Al-Caleb", YinzBurgh "LaPorta Potty" (Sleeper's `is_me` flag, not the league's top team).
- `data_api.py` (370 lines) re-exports entry points that live in private sibling modules (`_engine`, `_lineup`, `_market`, `_outlook`, `_schemas`). Tests patch only `data_api.leagues` (`tests/test_app_pages.py`, `tests/test_data_api_engine.py`), so keep any function that calls `leagues` in `data_api.py`, and never call it from a `_`-module.
- The learned model's past-game projections for 2019 and 2020 come from models that saw later seasons, so `store.projection_table()` drops them; never fit residual sizes or effects on them. Model features must use only games before the target game: pass a horizon shift to every lagged join (`learn.lag_asof`, `latest_asof`), and add a test.
- FantasyPros weekly rankings (`nfl_ecr`) are private-use only: keep them under the gitignored `data/` and never commit or share them. No paid data (user decision, 2026-10-23).
- `environment_layer = false` in `config.toml`: the corner and offense-efficiency adjustments had no held-out gain on the learned projections. The stage and code remain.
- Held-out checks: `learn` prints the learned model against the size-calibrated baseline; `backtest` adds pinball and coverage by size tier; `research/ros_check.py` (rest-of-season sums), `layers_check.py`, `availability_check.py`. Run `uv run python -m fantasy.stages.learn`, `availability` and `backtest` after changing a feature.

## Standard for model changes

A change to a projection or distribution ships only if it improves held-out error (fit 2019 to 2023, score 2024 on) or has a clear t-statistic (|t| of 2 or more) and the stages and tests pass. Record every test, shipped or not, with numbers in `docs/decisions.md`. Scripts behind past tests are in `research/` (see its README). Rejected ideas are listed there; read them before re-proposing one.

## Dates that matter (2026 season)

- Trade deadline: week 11. Issue #40 (retest the 50% Sleeper blend weight on clean snapshots) is due around then.
- `make odds` costs about 80 of 500 monthly credits per snapshot.
