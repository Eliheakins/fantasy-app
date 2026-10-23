# Architecture spec (from the ecc:architect agent, 2026-10-23)

Status: merged into the plan on 2026-10-23. The "Problems the agent found" list at the bottom was resolved (see decisions.md). Items marked "not checked" were not verified by the agent. Canonical backlog: docs/backlog.md.

## Repo layout

```
pyproject.toml  uv.lock  Makefile  config.toml
src/fantasy/
  config.py   store.py (paths, atomic parquet write, column schemas, DuckDB views)
  sources/    sleeper.py  nfl.py
  scoring.py  (pure: stats x league settings -> points)
  models/     baseline.py  kdef.py
  sim/        engine.py (Monte Carlo)  lineup.py (slot eligibility, greedy, top-K enumeration; no solver)  season.py
  stages/     sync_sleeper crosswalk ingest_nfl score project simulate decide backtest
  data_api.py (the only module the UI imports)
app/          Home.py  pages/{Lineup,Waivers,Trades,Outlook}.py
tests/        pytest checks for scoring, sim math, and config
data/         gitignored: raw/ derived/ archive/
```

## Storage

Parquet is the source of truth. DuckDB runs in memory as views over the files. No persistent .duckdb file, so Streamlit reads never fight a refresh over DuckDB's single-writer lock.

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

Each stage runs as `uv run python -m fantasy.stages.X --season S --week W`. It reads only named parquet files and writes only its own, via temp file then rename. Column names and dtypes live in one dict in store.py and are asserted on read and write. The CLI plus that dict is the contract, so a replacement in another language only has to honor both. Exception: trade evaluation is interactive, so sim/ is also a Python library that the data layer calls directly.

## Refresh

- `make refresh` runs all stages in order. Each skips itself while its output is within TTL: sleeper_players 24h; rosters, matchups, trending every run (about 10 calls); nflverse tables 12h; projections and sims whenever their inputs change.
- `make gameday` runs only sync_sleeper and simulate, to pick up injury status and locks. Players whose kickoff has passed (from schedules) are held fixed in lineup.py.
- Run by hand or with a dashboard Refresh button that calls the same stages. Optional launchd job: daily, plus Thursday and Sunday before kickoff (launchd running missed jobs on wake: not checked).
- Every raw pull is cached. Projections are archived every week and never overwritten, because point-in-time history cannot be rebuilt later. `st.cache_data` is keyed on file modification time.

## Config

`config.toml` (committed, nothing secret) holds season, user_id, `[leagues.colgate] id`, `[leagues.yinzburgh] id`, n_sims, playoff_week. Scoring is never set by hand: sync_sleeper stores each league's settings, and scoring.py applies one map from Sleeper stat keys to nflverse columns. Any nonzero key it cannot map stops the run with an error. Superflex comes from roster_positions.

## Data layer (the only module the UI imports)

`leagues()`, `roster()`, `lineup(league, week, objective)`, `waivers()`, `season_odds()`, `kdef()`, `unmatched()`, `evaluate_trade(league, give, get)`. All return Polars DataFrames. The UI does no SQL or math. A React front end later is FastAPI wrapping these functions.

## Expansion points

- **Dynasty:** models/aging.py, an asset_values table (DynastyProcess, FantasyCalc) keyed by sleeper_id, and a multi-season horizon in decide.
- **Props:** sources/odds.py and a snapshot_props stage writing archive/props (game_id, player, market, line, price, snapshot_at). Names are matched into id_map. project uses the data once enough history exists. The API key comes from an environment variable.
- **News LLM:** a news stage writes news_events (sleeper_id, ts, role_change, games_out), which project applies as adjustments.
- **React:** FastAPI over data_api.py, no engine changes.

## Problems the agent found in the plan

1. plan.md contradicts the one-pager (odds and weather in the data store, decision tools after own models, trades as a market-value blend, a chat assistant). Mark plan.md superseded.
2. K/DEF "Vegas totals, weather" at $0: nflverse schedules probably carries spread, total and roof (verify in E2). Forecast weather needs another source, so use roof only for the MVP.
3. The bar a model must beat is stated two ways: decisions.md says "consensus blend", the one-pager says "baseline". If `load_ff_rankings` has no current-week projections there is no consensus at all, and even if it does there is no archived history to backtest against. Make the baseline the bar and start archiving consensus now.
4. Title odds need rest-of-season projections for every rostered player in both leagues, plus an assumed opponent behavior (start the highest-mean lineup, make no adds). E3 must project the rest of the season, not one week.
5. Future-week matchup pairings from Sleeper are unverified. Spike in E4.
6. Over-built for the MVP: Gaussian copula (a shared team-game shock does the job), Kalman and changepoint breakout detection, conformal calibration, Weibull return times, and 50k sims inside an interactive partner finder (use about 5k with common random numbers).
7. "DuckDB plus parquet" is two stores. Keep parquet.

Risk to watch: if the ID crosswalk or future matchup pairings fail, E1 and E4 lose their foundations.
