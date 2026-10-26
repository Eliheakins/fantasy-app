# Architecture spec (from the ecc:architect agent, 2026-10-23)

Status: merged into the plan on 2026-10-23. The "Problems the agent found" list at the bottom was resolved (see decisions.md). Items marked "not checked" were not verified by the agent. Canonical backlog: docs/backlog.md.

## Repo layout

```
pyproject.toml  uv.lock  Makefile  config.toml
src/fantasy/
  config.py  store.py  scoring.py (pure: stats x league settings -> points)
  api.py  api_routes.py  api_models.py  api_jobs.py  api_envelope.py   FastAPI app (make serve)
  data_api.py  _*.py   read layer the API calls, and its private modules (_engine, _lineup, ...)
  live_refresh.py      score refresh while make serve runs
  sources/    sleeper.py  (Sleeper client)
  stages/     one module per stage, run as python -m fantasy.stages.<name>
  sim/        pure logic: sampler, lineup (greedy, no solver), season, moves, injuries, blend, odds
web/          React UI (Vite, TypeScript); pages in web/src/pages, nav in web/src/nav.ts
tests/        pytest suite
data/         gitignored: raw/ derived/ archive/
```

## Storage

Parquet is the source of truth. This is the design-time table: the current 46 tables are the keys of `store.SCHEMAS` (for example `nfl_player_stats` replaced `nfl_weekly`).

| Table | Key | Writer | Readers |
|---|---|---|---|
| sleeper_players | sleeper_id | sync_sleeper | crosswalk, decide, UI |
| leagues (scoring_settings, roster_positions) | league_id | sync_sleeper | score, project, simulate |
| rosters | league_id, roster_id, sleeper_id | sync_sleeper | simulate, decide |
| matchups | league_id, week, roster_id | sync_sleeper | simulate |
| trending | sleeper_id, fetched_at | sync_sleeper | decide |
| nfl_weekly / snaps / injuries / ff_opp | gsis_id, season, week | ingest_nfl | score, project |
| nfl_schedules | game_id | ingest_nfl | project, simulate |
| id_map | sleeper_id | crosswalk | all NFL joins |
| player_points | league_id, gsis_id, season, week | score | project, backtest |
| proj_points (archive) | league_id, sleeper_id, season, week, model, made_at | project | simulate, backtest |
| kdef_stream | season, week, team, pos | project | UI |
| sim_week, lineup_rec, sim_season | league_id, week, roster_id | simulate | UI |
| waiver_rec | league_id, week, sleeper_id | decide | UI |

## ID mapping

The crosswalk tries, in order:
1. The Sleeper ID column in `load_ff_playerids`, if the data spike confirms it exists.
2. ID fields inside the Sleeper players file (gsis_id may be one; not checked).
3. Exact normalized name + position + team.
4. For DEF: the Sleeper team code maps to a team key.

A `match_method` column records which step matched. With no match, gsis_id is null but the player stays: he gets a wide replacement-level prior for his position and shows on an "Unmatched" list in the dashboard.

## Stage contracts

Each stage runs as `uv run python -m fantasy.stages.X` (most take no arguments). It reads only named parquet files and writes only its own, via temp file then rename. Column names and dtypes live in one dict in store.py and are asserted on read and write. The CLI plus that dict is the contract, so a replacement in another language only has to honor both. Exception: trade evaluation is interactive, so sim/ is also a Python library that the data layer calls directly.

## Refresh

- `make refresh` runs all stages in order. Each skips itself while its output is within TTL: sleeper_players 24h; rosters, matchups, trending every run (about 10 calls); nflverse tables 12h; projections and sims whenever their inputs change.
- There is no `make gameday`. While `make serve` runs, `live_refresh.py` runs `sync_week` and then `simulate.run(archive=False)` every 10 minutes while games are on. Players whose kickoff has passed (from schedules) are held fixed in lineup.py.
- Run by hand (`make refresh`). The Refresh scores button re-pulls Sleeper matchups only.
- Every raw pull is cached. Projections are archived every week and never overwritten, because point-in-time history cannot be rebuilt later. The API caches league inputs per data version (`_engine`).

## Config

`config.toml` (committed, nothing secret) holds season, username, user_id, `[leagues.colgate] id`, `[leagues.yinzburgh] id`, n_sims, projection_model and environment_layer. Scoring is never set by hand: sync_sleeper stores each league's settings, and scoring.py applies one map from Sleeper stat keys to nflverse columns. Any nonzero key it cannot map stops the run with an error. Superflex comes from roster_positions.

## Data layer (the only module the API reads from)

`data_api.py` is the read layer; `api_routes.py` maps its functions to the `/api/leagues/{league}/...` routes. The function list below is the design-time list, so check `data_api.py` for current names. All return Polars DataFrames. The UI does no SQL or math. The React front end in `web/` calls FastAPI, which wraps these functions.

## Expansion points

- **Dynasty:** models/aging.py, an asset_values table (DynastyProcess, FantasyCalc) keyed by sleeper_id, and a multi-season horizon in decide.
- **Props:** `make odds` (`stages/snapshot_odds.py`) archives prop lines (needs `ODDS_API_KEY`). Nothing downstream reads them yet.
- **News LLM:** a news stage writes news_events (sleeper_id, ts, role_change, games_out), which project applies as adjustments.
- **React:** done (`web/`, FastAPI over `data_api.py`).

## Problems the agent found in the plan

1. plan.md contradicts the one-pager (odds and weather in the data store, decision tools after own models, trades as a market-value blend, a chat assistant). Mark plan.md superseded.
2. K/DEF "Vegas totals, weather" at $0: nflverse schedules probably carries spread, total and roof (verify in E2). Forecast weather needs another source, so use roof only for the MVP.
3. The bar a model must beat is stated two ways: decisions.md says "consensus blend", the one-pager says "baseline". If `load_ff_rankings` has no current-week projections there is no consensus at all, and even if it does there is no archived history to backtest against. Make the baseline the bar and start archiving consensus now.
4. Title odds need rest-of-season projections for every rostered player in both leagues, plus an assumed opponent behavior (start the highest-mean lineup, make no adds). E3 must project the rest of the season, not one week.
5. Future-week matchup pairings from Sleeper are unverified. Spike in E4.
6. Over-built for the MVP: Gaussian copula (a shared team-game shock does the job), Kalman and changepoint breakout detection, conformal calibration, Weibull return times, and 50k sims inside an interactive partner finder (use about 5k with common random numbers).
7. A second store beside parquet (for example DuckDB) is not needed. Keep parquet.

Risk to watch: if the ID crosswalk or future matchup pairings fail, E1 and E4 lose their foundations.
