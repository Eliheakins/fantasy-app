# fantasy-app

Personal NFL fantasy decision tool (Sleeper, redraft, two leagues). Local only, $0, Python 3.12 with uv.

## Commands

- `make setup`: install dependencies and enable the git hook
- `make check`: ruff, mypy and pytest, plus web typecheck and tests. Run before committing.
- `make fmt`: auto-fix lint and formatting

## Run it

- `make refresh`: back up `data/archive/`, then pull Sleeper and nflverse and rebuild every table (needs the network)
- `make serve`: build `web/` and serve the React UI plus the API at http://127.0.0.1:8000. `make dev`: API plus the Vite dev server (hot reload)
- `make schedule-install` / `schedule-remove`: a macOS launchd job running `make refresh` Tuesday 06:00, Friday 18:00 and Sunday 08:00 (Mac awake; log in `data/refresh.log`). Installed on the main Mac on 2026-10-28; `make schedule-remove` undoes it.
- `make odds`: archive one week of prop lines (needs `ODDS_API_KEY` in env or `.env`, gitignored; free tier is 500 credits a month, a snapshot costs about 80)
- Checks against real data: `uv run python -m fantasy.stages.validate_scoring`, `validate_standings`, `backtest`, `calibration`
- Never pipe `make check` into `tail` before committing: the pipe hides a failing exit code

## Where things are

- Plan: `docs/one-pager.md`. Backlog: `docs/backlog.md` (canonical story IDs). Decisions log: `docs/decisions.md`.
- Research: `research/README.md` indexes every test script by topic with its status; plans and surveys are in `research/notes/`.
- Log every decision in `docs/decisions.md` as it is made.

## Conventions

- Parquet under `data/` (gitignored) is the source of truth. Stages and `data_api.py` read it with polars; DuckDB is not a dependency (add it back only if a query needs it).
- The API (`src/fantasy/api*.py`) reads through `fantasy.data_api`; `api_routes.py` also imports `_engine` and `_view`. `make check` also typechecks and tests `web/`.
- No secrets in the repo. API keys come from environment variables.
- Lean MVP: simplest method that works, tests only for math and config, no CI.
- Sleeper's API is read-only. Stay under 1,000 calls a minute and fetch the players file at most once a day.
- Annotate function signatures. Prefer frozen dataclasses.

## How it fits together

Stages (`src/fantasy/stages/`, run by `make refresh` in this order) read and write parquet tables registered in `store.SCHEMAS`. `src/fantasy/sim/` holds the pure logic; `stages/simulate.py` builds a `LeagueData` from the tables and `data_api.py` serves it to the API in `src/fantasy/api*.py`, which the React app in `web/` calls.

0. `backup` (copies `data/archive/` out of the repo), then:
1. `sync_sleeper`, `news_archive` (daily Sleeper status snapshot from the cached players file), `sleeper_projections`, `ingest_nfl`, `crosswalk`: raw data and the Sleeper to nflverse ID map.
2. `score`, `prop_points`, `streaming`: points per league's scoring; this week's prop-implied points (latest `make odds-slate` snapshot) and FFToday points (`proj_props`, `proj_outside`); K and DEF.
3. `project`: rolling baseline (`proj_baseline`). `learn`: gradient-boosted model on lagged stats plus role data (`proj_learned`, same schema; `projection_model` in `config.toml` picks which one every later stage reads, through `store.projection_table()`; with `stat_line_model` on (off by default in the loader, on in `config.toml`), `learn` multiplies by the chance of a stat line from `stages/stat_line.py`, so `proj_learned` is expected points given a played game (offensive snaps or a `player_points` row; no row scores 0), with past rows for games without a stat line too; q goes to the `stat_line` table (`stat_line_table.py`, written after `proj_learned`, deleted when off), which the injury layer and the `injuries` stage use to take q back out where the injury table's chance of playing already counts it). `availability`: chance of playing this week (`availability`). `distributions`: size calibration, per-tier marginals and spreads, correlations, fit on the chosen projections. `streaming` projects K and DEF with a ridge on trailing form, implied total and (K) team and kicker features (`streaming_model.py`), blended with Sleeper's, and archives each run in `streaming_snapshots`.
4. `injuries`, `outlook`, `environment`: measured effects (tables `injury_effects`, `outlook_effects`, `environment_effects`).
5. `simulate`: applies calibration, the source blend (`sim/blend.py`: current week the equal mean of ours and each `blend_sources` entry a player has, the next three weeks ours and Sleeper), injury (with the availability model for a flagged player's next game), outlook and, if `environment_layer` is on, environment layers, then season odds. Each team's K and DEF slots use its best rostered unit's projection (`LeagueData.kd_slot`, built by `simulate._kd_slot_projections`; league mean where a team has none), with the league-wide spread.
6. `digest`, `market_values`: the digest's stored waiver and trade ideas (`move_ideas`) and FantasyCalc market values, both after `simulate`.

A missing table for a layer in step 4, or for calibration or a blend source, is skipped without error; the stale banner lists what is missing (`data_api.missing_layers`).

## Gotchas

- `data/` is gitignored. A fresh clone has no data: run `make setup`, then `make refresh` (needs the network).
- `data/archive/` cannot be regenerated: our own weekly projections for the next game (`proj_snapshots`, the clean test of the learned model), Sleeper projection snapshots (re-stamped by the endpoint after games, so only our own snapshots are clean), odds snapshots, season-odds history, K and DEF projections (`streaming_snapshots`), daily Sleeper status snapshots (`sleeper_player_status`, for `research/news_residual_check.py`). `make backup` copies it to `~/fantasy-app-backups` (or `FANTASY_BACKUP_DIR`; keep 30) and `make refresh` runs it first. Never put the copy in a repository. Issue #40 depends on it.
- Point-valued effects are measured in the reference league (lowest league id) and scaled per league (`sim/scoring_scale.py`). Add a new point-valued effect to the `*_POINT_KINDS` sets in `stages/simulate.py`, or YinzBurgh (0.5 PPR) will be overstated.
- My teams: Colgate "Lisan Al-Caleb", YinzBurgh "LaPorta Potty" (Sleeper's `is_me` flag, not the league's top team).
- `data_api.py` (571 lines) re-exports entry points that live in private sibling modules (`_engine`, `_lineup`, `_market`, `_outlook`, `_schemas`, and others). Tests patch `data_api.leagues` (`tests/test_api.py`, `tests/test_data_api_engine.py`), so keep any function that calls `leagues` in `data_api.py`, and never call it from a `_`-module.
- The learned model's past-game projections for 2019 and 2020 come from models that saw later seasons, so `store.projection_table()` drops them; never fit residual sizes or effects on them. Model features must use only games before the target game: pass a horizon shift to every lagged join (`learn.lag_asof`, `latest_asof`), and add a test.
- FantasyPros weekly rankings (`nfl_ecr`) are private-use only: keep them under the gitignored `data/` and never commit or share them. No paid data (user decision, 2026-10-23). A free source may be scraped and stored unless its terms explicitly forbid it (user decision, 2026-10-26; sources checked so far are in `research/notes/2026-10-26-research-survey.md`); third-party data is never committed. YinzBurgh's earlier seasons (2023 to 2025) are on ESPN, private, league id 1470881390: `research/espn_fetch.py` needs `ESPN_S2` and `ESPN_SWID` in `.env` (never in a command or chat) and saves raw JSON under the gitignored `research/scratch/espn/`; `espn_parse.py` makes lineup tables there. Fetched and parsed on 2026-10-28; only research checks read it, nothing in the pipeline. Colgate has no earlier seasons.
- `make serve` also runs a live refresh every 10 minutes while a game of the current week is on (`live_refresh.py`: `sync_week` then `simulate.run(archive=False)`; `LIVE_REFRESH=off` disables it). Never let a live tick append to `sim_season_history`.
- Team selector: `?team=<roster id>` on any `/api/leagues/{league}/...` route makes that team 'me' (`_engine.viewing_team`). Anything that decides 'my team' must go through `_league()` or `data_api._my_league`, never read `league_teams.is_me` directly.
- Lineup values for the current week include players whose game is over at their actual points (`_engine._week_values`); do not read `moves.week_values` directly for a current-week lineup.
- API: non-GET requests need the header `X-Requested-With: fantasy-app`; the server binds 127.0.0.1 and rejects unknown Host headers (extra names come from `API_ALLOWED_HOSTS`, comma separated). Phone access only through `tailscale serve`, never funnel. `web/openapi.json` is generated (`uv run python -m fantasy.api --openapi`); never put `nfl_ecr` data in it or in fixtures.
- `project.future_targets` starts at the league's `current_week` and keeps only games with no score yet (a Thursday game in the data must not hide week N for other teams). Scores enter data on `make refresh`, the Refresh scores button and the live refresh in `make serve` (during games). Run `make refresh` after Sunday and after Monday night, and after Friday's injury report: `learn`'s teammate-vacancy features (`stages/vacancy.py`) use each gameday's final report once it is published and only Sleeper's Out players before that.
- `environment_layer = false` in `config.toml`: the corner and offense-efficiency adjustments had no held-out gain on the learned projections. The stage and code remain.
- Held-out checks: `learn` prints the learned model against the size-calibrated baseline; `backtest` adds pinball and coverage by size tier; `research/ros_check.py` (rest-of-season sums), `layers_check.py`, `availability_check.py`. Run `uv run python -m fantasy.stages.learn`, `availability` and `backtest` after changing a feature.

## Standard for model changes

A change to a projection or distribution ships only if it improves held-out error (fit 2019 to 2023, score 2024 on) or has a clear t-statistic (|t| of 2 or more) and the stages and tests pass. Held-out error is judged on all played games (offensive snaps or a stat row; a played game with no stat row scores 0; `learn.hurdle_on_played`), with the `compare_to_baseline` rows reported alongside (user decision, 2026-10-26). Record every test, shipped or not, with numbers in `docs/decisions.md`. Scripts behind past tests are in `research/` (see its README). Rejected ideas are listed there; read them before re-proposing one.

## Dates that matter (2026 season)

- Trade deadline: week 11. Issue #40 (retest the 50% Sleeper blend weight on clean snapshots) is due around then.
- `make odds` costs about 80 of 500 monthly credits per snapshot.
