# Fantasy app one-pager (v3, 2026-10-23; status and limits refreshed 2026-10-28)

**Status:** every story except E3-8 is done and checked on live data (GitHub closes #18, E3-8, as completed, but the ECR points check is not in the code; all 36 E-series issues are closed): Home with actions and odds, Lineup with win probability and locks, Waivers with re-simulated odds and K/DEF streaming, Trades, and Outlook with seeds and schedule. Since then: replacement-level valuation, multi-player trades, an injury model, ceiling and floor start/sit, size calibration, a Player outlook page, a learned projection and chance-of-playing model, a teammate-vacancy feature, a weekly digest, per-team K and DEF (ridge model, used in the odds, lineups and win probability), a trade acceptance figure and a drop-risk watch. The README lists the pages and commands; `decisions.md` has every test with numbers; known gaps are at the top of `backlog.md`.

**Goal:** a local dashboard that tells me each week, for Colgate and YinzBurgh (Sleeper redraft): who to start, who to add, and which trades raise my title odds.

**Core idea:** score every decision by its effect on win probability, using simulated outcome ranges under each league's own scoring. Every recommendation carries a confidence tag (clear, lean, toss-up) from the share of paired simulations where it helps, with model uncertainty included.

## Architecture (Python, local on M5 Pro, $0)

Sleeper (read-only) and nflverse feed parquet files, read with polars (no DuckDB). The stages are listed in the README (`make refresh` order). Each reads and writes named parquet files, so any stage can change language later. The API reads through `data_api.py`. No optimization solver: lineups come from greedy slot fill. Details: `spec/architecture.md`.

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
| After | Players search, own model, dynasty, news LLM, draft assistant (partner finder and the React UI are built) | |

**Fast path to a working trade evaluator** (week 11 deadline, no value after it), 17 stories: E0-1, E0-2, E1-1, E1-2, E1-3, E2-1, E3-1 to E3-5, E4-1, E4-3, E4-4, E5-1, E5-3, E5-D2. Whether it fits before week 11 is not estimated. Cut order is in `backlog.md`.

## Dashboard (Streamlit first, now React)

The Streamlit app was removed in commit 0cd914c; the React UI in `web/` serves the pages (`web/src/nav.ts`). The original design: a decision queue with evidence. League selector (Both only on Home). Home cards with win probability and range bars, Lineup with a points versus win-probability toggle, Waivers, Trades with an explicit Evaluate button, Outlook. Color only for change (green and red), amber for injury and stale data. No dark toggle, no live recompute, no hover tooltips, no market values. Details: `spec/dashboard.md`.

## What the checks found

- **Works (real calls, week 6 data):** Sleeper IDs resolve for 16 of 17 players on each roster (the miss is the DEF), 90.9% of active players overall. Per-league scoring from nflverse matches Sleeper exactly for 161 of 169 offense and K starters, all 17 of yours, and 17 of 19 defenses.
- **Changed:** the free ranking data is expert ranks only, with no stat projections. The baseline is an in-house rolling expected-points model, and the model bar is "beat the baseline and be calibrated".
- **Math fixes from review:** one shared correlation factor was rejected (the measured WR with WR correlation is 0.02), a persistent per-player error was added so title odds are not overconfident, and the odds are labeled "assuming current rosters".
- **Limits:** Vegas lines only a few weeks ahead, weather only for the first weeks, nflverse stats lag a week, 9.1% of players need name matching or manual overrides, no past seasons in Sleeper (backtests use nflverse history with synthetic 1.0 and 0.5 PPR settings; the real-league checks cover 2026 weeks 1 to 7; YinzBurgh's 2023 to 2025 seasons are on ESPN and not loaded).
- **Marginal by nature:** win-probability lineups usually match max-points lineups, so the app says so instead of inventing a swap.

## Open items

- FantasyPros ECR via nflverse: used as learned-model features under private use (decision of 2026-10-23); it is never shared (`data/` is gitignored).
- DEF scoring: some team-weeks differ from Sleeper's by 1 to 2 points (likely special-teams recoveries), cause not traced.
- Sleeper future-week matchups and playoff settings: resolved; the bracket is 6 teams, byes for seeds 1 and 2, weeks 15 to 17 (confirmed by the user).
- Measured: tau, CVs, calibration, injury and outlook effects. Assumed: the weekly roster drift and the 50% Sleeper blend weight (retest around week 11, #40).
- Odds API free key: in `.env` (E2-2 is done); `make odds` costs about 80 of 500 monthly credits.
