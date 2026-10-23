# Fantasy app one-pager (v3, 2026-10-23)

**Goal:** a local dashboard that tells me each week, for Colgate and YinzBurgh (Sleeper redraft): who to start, who to add, and which trades raise my title odds.

**Core idea:** score every decision by its effect on win probability, using simulated outcome ranges under each league's own scoring. Every recommendation carries a confidence tag (clear, lean, toss-up) from the share of paired simulations where it helps, with model uncertainty included.

## Architecture (Python, local on M5 Pro, $0)

Sleeper (read-only) and nflverse feed parquet files, with DuckDB as in-memory views. Stages: `sync_sleeper`, `crosswalk`, `ingest_nfl`, `score`, `project`, `simulate`, `decide`. Each reads and writes named parquet files, so any stage can change language later. The dashboard reads one module, `data_api.py`. No optimization solver: lineups come from greedy slot fill. Details: `spec/architecture.md`.

## Epics (Kanban, 36 stories, one session each: `backlog.md`)

| Epic | Scope | Panel it ships |
|---|---|---|
| E0 | Repo, store, board | none |
| E1 | Sleeper sync (plus a spike on future matchups and playoff settings), ID crosswalk | Home roster and scoring, freshness footer |
| E2 | NFL data store, free-tier prop snapshots | none |
| E3 | Per-league scoring, rolling baseline with walk-forward history, distributions, backtest, persistent-error scale, K/DEF rules | none |
| E4 | Lineup fill, schedule and playoffs, season simulator, win-probability lineup, calibration, locks | Lineup, Home cards, Outlook |
| E5 | Waiver ranking, trade evaluator, deadline guards | Waivers, Trades, Home actions |
| **MVP line** | | |
| After | Partner finder, Players search, own model, FAAB and CHOPPA, dynasty, news LLM, React UI, draft assistant | |

**Fast path to a working trade evaluator** (week 11 deadline, no value after it), 17 stories: E0-1, E0-2, E1-1, E1-2, E1-3, E2-1, E3-1 to E3-5, E4-1, E4-3, E4-4, E5-1, E5-3, E5-D2. Whether it fits before week 11 is not estimated. Cut order is in `backlog.md`.

## Dashboard (Streamlit, rough first)

A decision queue with evidence. League selector (Both only on Home). Home cards with win probability and range bars, Lineup with a points versus win-probability toggle, Waivers, Trades with an explicit Evaluate button, Outlook. Color only for change (green and red), amber for injury and stale data. No dark toggle, no live recompute, no hover tooltips, no market values. Details: `spec/dashboard.md`.

## What the checks found

- **Works (real calls, week 6 data):** Sleeper IDs resolve for 16 of 17 players on each roster (the miss is the DEF), 90.9% of active players overall. Per-league scoring from nflverse matches Sleeper exactly for 161 of 169 offense and K starters, all 17 of yours, and 17 of 19 defenses.
- **Changed:** the free ranking data is expert ranks only, with no stat projections. The baseline is an in-house rolling expected-points model, and the model bar is "beat the baseline and be calibrated".
- **Math fixes from review:** one shared correlation factor was rejected (the measured WR with WR correlation is 0.02), a persistent per-player error was added so title odds are not overconfident, and the odds are labeled "assuming current rosters".
- **Limits:** Vegas lines only through week 8, weather null from week 5, nflverse stats lag a week, 9.1% of players need name matching or manual overrides, no past seasons in your leagues (backtests use nflverse history with synthetic 1.0 and 0.5 PPR settings; the only real-league check is 2026 weeks 1 to 7).
- **Marginal by nature:** win-probability lineups usually match max-points lineups, so the app says so instead of inventing a swap.

## Open items

- FantasyPros ECR via nflverse: redistribution terms unchecked, so nothing depends on it.
- DEF scoring: 2 of 19 mismatched, cause not traced.
- Sleeper future-week matchups and playoff settings: spike is the first part of E1-1.
- All spread and error constants (tau, CVs, play probabilities) are provisional until the backtest.
- Odds API free key: needed for E2-2.
