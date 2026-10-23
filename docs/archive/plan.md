# Plan (v0, 2026-10-22)

SUPERSEDED (2026-10-23). Current plan: [one-pager.md](../one-pager.md) and [backlog.md](../backlog.md). This file is kept as the original brainstorm. It differs from the current plan in several ways (odds and weather in the data store, decision tools after own models, trades as a market-value blend, a chat assistant, DuckDB plus parquet).

Scope: NFL redraft, Sleeper, 2 leagues, local app. See decisions.md.

## Data sources (free or cheap)

| Source | Use |
|---|---|
| Sleeper API | Rosters, matchups, transactions, drafts, league scoring settings, trending adds. Public, no login. Rate limit recalled as about 1,000 calls/minute, not verified. |
| nflverse (`nflreadpy`) | Play-by-play, weekly stats, snap counts, injuries, expected fantasy points, ID crosswalk to Sleeper IDs. |
| DynastyProcess data (`dynastyprocess/data`) | Open values, rankings, ID mappings. |
| FantasyCalc | Free trade-value API. |
| The Odds API | Player prop lines. Free tier, about $30/month if needed. |
| Open-Meteo | Free weather. |

Prior art to copy from: `nmelhado/league-page` (Sleeper league site), `nflverse/*`, `dynastyprocess/data`, `cameron-eth/sleeper-sdk` (Python Sleeper wrapper).

## Features and models

| Feature | Model | Run cost |
|---|---|---|
| Roster and league sync | None. Fetch, store, crosswalk IDs. | Free |
| Player projections as distributions | LightGBM quantile models or Bayesian hierarchical models. Features: usage, expected points, team implied total, weather, prop lines. Conformal calibration. | Minutes on CPU, weekly |
| Start/sit | Maximize win probability, not expected points. Monte Carlo with Gaussian copula for same-team correlation, then integer programming for the lineup. | Milliseconds per league |
| Rankings and value | Value over replacement using the league's real scoring and roster slots. | Free |
| Trade analyzer | Market values blended with roster need and win-now/rebuild discounting. Key output is the change in title odds from the season simulation. Partner search for mutually beneficial trades. | Free |
| Season simulation | 50k Monte Carlo runs of the remaining schedule. Playoff and title odds, luck metrics (all-play record, Pythagorean expectation). | Seconds |
| Waivers | Player value is the gain in win probability over the horizon. Breakout detection with a Kalman filter on target and snap share, plus changepoint detection. | Free |
| Draft assistant | Plackett-Luce model of other teams' picks fit to ADP. Roll out the draft many times, pick the player that maximizes expected final team strength. | Seconds per pick |
| Injury and news | Small LLM turns news into structured fields (role change, games missed). Weibull survival model for return timing. | About $1 to $5/month |
| Chat assistant | LLM calling the models as tools. It does not do the math itself. | Cents per day |

## Architecture

One Python repo with `ingest`, `features`, `models`, `sim`, `app` packages. Storage is DuckDB plus parquet. A local scheduler (cron or launchd) runs the nightly ingest and the weekly retrain. Local UI (Streamlit or a terminal UI). Estimated cost $0 to $35/month in season, almost nothing in the offseason.

## Build order

1. Sleeper sync, ID crosswalk, roster view.
2. Market-based start/sit and trade values from consensus data (most of the value, no ML).
3. Simulation engine: season odds and the win-probability lineup optimizer.
4. Own projections, shipped only if they beat the consensus blend out of sample.
5. Waivers, draft assistant, news LLM.

## Rough buildout (2026-10-22)

Each phase ends with something usable. The season is already in progress, so phases 1 to 4 and 6 matter first. The draft assistant can wait until next August.

0. **Foundation:** personal repo, Python env, DuckDB, config holding the Sleeper username.
1. **Read my teams:** Sleeper client for leagues, rosters, scoring settings, matchups, the players file. ID crosswalk to nflverse. Done when a CLI prints both leagues with the right scoring.
2. **Data store:** nflverse weekly stats, snaps, injuries, schedule, plus odds lines and weather. Scheduled refresh. Done when any player's history is queryable by Sleeper ID.
3. **Baseline and backtest:** consensus-based projections scored under each league's settings, plus a walk-forward backtest harness. Built before any custom model so every later model has a bar to beat.
4. **Simulation engine:** player outcome distributions, correlation, lineup optimizer (start/sit by win probability), season and title odds. First phase that gives weekly decisions.
5. **Own projection models:** quantile gradient boosting. Ships only if it beats the baseline in backtests.
6. **Decision tools:** waiver ranking, trade analyzer, value over replacement.
7. **Draft assistant:** needed by next August.
8. **News LLM, chat assistant, UI polish.**

Order: 0, 1, 2, 3, 4, then 5 and 6 in either order, then 7 and 8.

## Open questions

- Whether any league has a non-standard scoring format that changes the replacement-level math. Pull the exact settings from the Sleeper API in step 1.
- Which UI to use locally (Streamlit versus terminal).
