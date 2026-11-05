# fantasy-app

A personal NFL fantasy football decision tool for [Sleeper](https://sleeper.com) redraft leagues. It runs locally, costs nothing, and answers the weekly questions: who to start, who to add or drop, which trades help, and how likely each team is to make the playoffs and win the title.

It is built for two leagues (Colgate, 10 teams, superflex, 1.0 PPR; YinzBurgh, 10 teams, 0.5 PPR), but nothing is hard-coded beyond `config.toml`. Single user, no login, not deployed.

> Lean on purpose: the simplest method that works, tested where the math is, no CI. Decisions and the evidence behind them are in [docs/decisions.md](docs/decisions.md).

## What it does

Every recommendation is scored by its effect on **win probability or title odds**, using simulated outcome ranges under each league's own scoring, not by projected points alone.

The five tabs are This week, Lineup, Moves, Season and Players; the week picker in the top bar sets one `?week=` for every page. Old paths (`/waivers`, `/trades`, `/outlook`, `/scoreboard`, `/league`, `/digest`, `/scorecard`, `/explore`) redirect and keep the query.

| Page | Answers |
|---|---|
| **This week (`/`)** | One to-do list for both leagues, ordered by what expires first and then by effect, a Tuesday to Monday week strip with now, waiver clears, the Friday injury report and kickoffs, and "Since you last looked" per league (odds change, status changes of your players, new waiver adds; the last visit is kept in this browser). Under "League details": season odds for both leagues (playoffs, bye, title), this week's score so far and chance to win, and a "Do this now" list across lineup, waivers and trades. Refresh scores during games. Below it, the digest: Last week's results, projection misses, the odds change since the last run, my top waiver adds and trade ideas (built by `make refresh`), and players to watch (falling snap share or market value, injury flags). |
| **Lineup (`/lineup`)** | The answer as the heading ("Start Cook at Flex", or "Your lineup is set"), your win chance and its change against what is set in Sleeper now, then the close calls: only slots where the starter beats the best eligible bench player in under 70% of paired simulations get a row (clear, lean or toss-up), the rest fold into "N slots are clear". Late-scratch fallbacks ("If Cook is out: start Bernard") for flagged starters, both teams' 10th to 90th score ranges, and full Start and Bench tables with floor, median and ceiling per player. "Other ways to pick" holds the four objectives (expected points, win probability, max ceiling, max floor); the page starts from max ceiling when you are the underdog and max floor when you are the favorite. Locked players (game started) are not suggested. |
| **Moves (`/moves`)** | Switch with `?view=fa` (default) or `?view=trades`. Free agents: Free agents ranked by how much they raise your odds over a replacement-level free agent, with the suggested drop. Streaming picks for defense and kicker. Trades: Evaluate any trade, or search for trades that raise both teams' odds: 1 for 1, 1 for 2, 2 for 1 and 2 for 2. Each shows the change in your playoff and title odds with a Monte Carlo error, the market-value balance, and how many past accepted trades in the leagues were as lopsided. |
| **Season (`/season`)** | Outlook: Playoff seed distribution and the remaining schedule with win chances. Scores: This week's matchups with live scores and each team's chance to win. League: Power rankings, luck (all-play record), manager grades, schedule strength and what-ifs. |
| **Players (`/players`)** | Player outlook: who is likely to improve or regress (return from injury, teammates out, injury risk). A player's name opens his page (`/players/:gsisId`): the answer (next game median and 10th to 90th range), then next game, rest of season points over the best other free agent at his position, snap and target share by week, why the model expects change, injury and chance to play, market value (today's only), owner and the season's game log. `/players/compare?p=...` puts two or three players side by side with the same sections. |
| **Find players (`/players/find`)** | Query NFL play-by-play in the browser: pin players or teams, pick up to five stats, set filters (season, down, situation), rank or split the rows, and chart two stats. With a league selected, League points is a stat (fantasy points under that league's scoring, regular season, players only, no play filters), and a League filter (All players, My roster, Rostered, Free agents, all as of today's rosters and for the viewed team) restricts player rows and rankings, and result rows show the owning team. Needs `make stat-data`. Saved searches keep named queries in this browser to run again. Clicking a player's name anywhere opens that player's page (`/players/:gsisId`), which also has an Open in Explore link. |
| **Ask (`/ask`)** | Ask an NFL stats question in plain language, like "Mahomes passing yards and touchdowns in 2023". Built-in rules read what they can and a local model (`make ask-model`) reads the rest; the numbers come from the same browser engine as Explore, and "fantasy points" or "league points" use the selected league's scoring. Start/sit questions ("start Kelce or Kittle", "Kelce or Kittle this week") are read by the rules alone and answered from the Lineup projections: the recommendation, the points gap and both 10 to 90% ranges, with a link to compare the two players. Trade questions ("trade Kelce for Kittle", "Kelce and Hill for Kittle trade") are read by the rules too and answered with the Trades page's evaluation for the team that owns the player you would get: the change in both teams' playoff and title odds. Players on several teams or free agents hand off to the Trades page. The box in the top bar opens Ask with your question. The History tab keeps what you asked in this browser. Needs `make stat-data`. Opened from the Ask field in the top bar. |
| **Model (`/model`)** | Scorecard of the learned, baseline and Sleeper projections against actual points. Linked from the footer. |

## How the numbers are made

1. **Learned projection.** A gradient-boosted model predicts a player's points when he plays from lagged weighted averages of points, expected points, volume, snap and target share, team pace, advanced stats, depth chart, age and draft pick, FantasyPros weekly rankings (private use) and the game's Vegas lines. Each past season is scored by a model that never saw it. On 2024 to 2026 it beats the rolling baseline below by about 2% RMSE and summed rest-of-season error by about 3.5%. `projection_model` in `config.toml` can switch back to the baseline. The rolling baseline: Each player's recent expected points (nflverse's opportunity model, which removes touchdown and yardage luck), blended 50/50 with actual points, exponentially weighted (half-life 4 games), shrunk toward a position average, and scaled by the game's Vegas implied team total. Scored under each league's rules.
2. **Size calibration.** The baseline over-projects low projections; a per-position piecewise-linear curve corrects it (out of sample: MAE 2.75% lower).
3. **Sleeper blend.** For the current week and the next three, our number is averaged 50/50 with Sleeper's (RotoWire) projection. The weight is an assumption until clean data exists (issue #40).
4. **Injuries.** For a flagged player's next game a classifier (depth rank, report, practice, snap trend) gives the chance of playing (5.9% better Brier than the table); for the next four games the table gives the chance from report status, practice participation and injury type, plus a discount when playing through it. Out of sample the Brier score on the current game improved from 0.219 (fixed rates) to 0.193.
5. **Outlook and environment effects.** (The environment half is off: no held-out gain.) First-games-back after missing time, teammates' vacated targets and carries, the opposing leading cornerback being out, and the offense's recent sack rate and pass efficiency. Applied only where the estimate is clear (|t| of 2 or more), and scaled to each league's scoring.
6. **Distributions.** Points around the projection use empirical quantile shapes per league, position and projection size, with correlations between teammates and opponents (Gaussian copula). Each player also has their own chance of not playing.
7. **Season simulation.** 20,000 runs of the rest of the season with a persistent per-player error, weekly roster drift, the playoff bracket (6 teams, byes for seeds 1 and 2, weeks 15 to 17), and common random numbers so that comparing two moves is low-noise.
8. **Decisions.** Waivers, drops and trades are valued over a replacement-level free agent (a backup tight end is worth little when many are free; a quarterback in superflex is worth a lot). Lineups are picked on one half of the simulated draws and scored on the other half, and a win-probability pick is recommended only if it also wins on the held-out half.

What was tried and **rejected** is as important as what shipped: per-player volatility, usage trends, opponent defense points allowed, rookie status, offensive and defensive line health, starting quarterback out, slot-corner matchups, a different Vegas exponent and head-to-head history against an opponent. FantasyPros rankings were first ruled out as a baseline, then tested as learned-model features, which they passed. Each has numbers in [docs/decisions.md](docs/decisions.md), and the scripts are in [research/](research/).

## Setup

Requires [uv](https://docs.astral.sh/uv/) (it installs Python 3.12) and a network connection for the first load.

```sh
make setup      # install dependencies, enable the pre-commit hook (ruff only)
make refresh    # pull Sleeper and nflverse and rebuild every table
make serve      # build the web UI and open it at http://127.0.0.1:8000
```

`data/` is gitignored, so a fresh clone has no data until `make refresh` runs. The app binds to `127.0.0.1` only because it has no login.

Configure your own leagues in [config.toml](config.toml) (Sleeper username, user id, league ids). It holds no secrets.

### Optional: prop-line snapshots

`make odds` archives one week of player prop lines from [The Odds API](https://the-odds-api.com) (free tier, 500 credits a month; one snapshot is about 80). Put the key in `.env` as `ODDS_API_KEY=...` (gitignored) or the environment. `make odds-slate` archives the current slate, and `prop_points` turns the latest snapshot into this week's prop-implied points.

## Commands

<!-- AUTO-GENERATED from the Makefile; edit the Makefile, not this table -->
| Command | What it does |
|---|---|
| `make setup` | Install dependencies and enable the pre-commit hook |
| `make refresh` | `make backup`, then rebuild all tables in order (needs the network) |
| `make backup` | Copy `data/archive/` to `~/fantasy-app-backups` (newest 30 kept) |
| `make check` | ruff, mypy and pytest, plus the web typecheck and tests. Run before committing. |
| `make test`, `make lint`, `make fmt` | pytest only; ruff and mypy only; auto-fix lint and formatting |
| `make serve` | Build the web UI and serve it and the API at http://127.0.0.1:8000 |
| `make dev` | API with reload plus the Vite dev server (hot reload for the UI) |
| `make web-build` | Build the web UI only |
| `make stat-data`, `make stat-data-refresh` | Build the nflverse play-by-play shards for the stat app into `data/stat` (all seasons; current season only). Needs the network and minutes |
| `make ask-model` | Local MLX model server for Ask (Apple Silicon). Ask answers rule-readable questions without it |
| `make odds`, `make odds-slate` | Archive one week of prop lines; archive the current slate |
| `make schedule-install`, `make schedule-remove` | Set up or remove a macOS launchd job that runs `make refresh` Tuesday 06:00, Friday 18:00 and Sunday 08:00 (installed on the main Mac on 2026-10-28) |
<!-- END AUTO-GENERATED -->

Checks against real data: `uv run python -m fantasy.stages.validate_scoring` (computed points against Sleeper's for a completed week), `validate_standings`, `backtest` (walk-forward baseline against a trailing average) and `calibration` (team-score distributions against completed weeks).

### Environment variables

<!-- AUTO-GENERATED from the os.environ reads in src/ and research/; edit the code, not this table -->
| Variable | Required | Used by | Meaning |
|---|---|---|---|
| `ODDS_API_KEY` | For `make odds` only | `stages/snapshot_odds.py` | The Odds API key (`.env` or environment) |
| `LIVE_REFRESH` | No | `live_refresh.py` | `off` stops the score refresh while `make serve` runs (default on) |
| `API_ALLOWED_HOSTS` | No | `api.py` | Extra Host header names the server accepts, comma separated (phone access) |
| `FANTASY_BACKUP_DIR` | No | `stages/backup.py` | Where `make backup` writes (default `~/fantasy-app-backups`) |
| `ESPN_S2`, `ESPN_SWID` | Only for `research/espn_fetch.py` | research script | ESPN login cookies for the private YinzBurgh history (`.env` only) |
<!-- END AUTO-GENERATED -->

During the season, run `make refresh` after games and before setting a lineup. The app shows a banner when data is stale or when a projection layer's stage has not run. This week's "Refresh scores" button re-fetches Sleeper matchups on demand. While `make serve` runs, it also refreshes scores every 10 minutes while a game of the current week is on (`LIVE_REFRESH=off` turns that off).

## Layout

```
config.toml            leagues and user (no secrets)
src/fantasy/
  api.py, api_routes.py  FastAPI app and /api routes (`make serve`)
  data_api.py          read layer over the parquet store (the API reads through it; _*.py hold the logic)
  live_refresh.py      score refresh while `make serve` runs
  store.py             parquet store: atomic writes, schema checks (store.SCHEMAS: 52 tables)
  scoring.py           Sleeper scoring settings applied to nflverse stat lines
  sources/             Sleeper client
  stages/              pipeline stages, each run as python -m fantasy.stages.<name>
  sim/                 pure logic: lineups, sampler, season simulation, moves, injuries, effects
src/nfl_stat/          the merged stat app backend: data build (`make stat-data`), Ask intent endpoint, shard serving
metrics/metrics.json   stat definitions (SQL, aliases) read by the stat app
web/                   React UI (Vite, TypeScript)
tests/                 pytest suite (tests/stat/ is the stat app's)
research/              one-off analysis scripts behind decisions.md
overrides/id_map.csv   manual Sleeper to nflverse ID overrides
docs/                  decisions log, backlog, one-pager, specs
```

Pipeline order (`make refresh`), <!-- AUTO-GENERATED from the Makefile --> `backup`, `sync_sleeper`, `news_archive`, `sleeper_projections`, `outside_projections`, `ingest_nfl`, `crosswalk`, `score`, `prop_points`, `streaming`, `project`, `learn`, `availability`, `distributions`, `injuries`, `outlook`, `environment`, `simulate`, `digest`, `market_values` <!-- END AUTO-GENERATED -->. Each stage reads and writes parquet tables under `data/` (`raw`, `derived`, `archive`) registered in `store.SCHEMAS`, so any stage can be replaced independently.

## Data sources

- **Sleeper** (read-only API): leagues, rosters, matchups, transactions, trending, players, and weekly projections from an undocumented endpoint. Calls stay well under 1,000 a minute and the players file is fetched at most once a day. Please keep the "Data from Sleeper" attribution if you build on this.
- **nflverse** (via `nflreadpy`): player stats, snaps, injury reports, schedules with Vegas lines, expected points, team stats and play-by-play efficiency.
- **FantasyPros** (via nflverse): weekly expert rankings, used as learned-model features under private use only. Never committed or shared (`data/` is gitignored).
- **FantasyCalc** (undocumented endpoint): market values for the trades view of Moves, fetched at most once a day per league setting.
- **The Odds API** (optional): prop lines, archived by `make odds` and used for this week's prop-implied points.
- **FFToday** (free pages): weekly outside projections (`proj_outside`).
- **ESPN** (private league, your cookies): YinzBurgh's 2023 to 2025 seasons, fetched by `research/espn_fetch.py` and parsed by `research/espn_parse.py` into the gitignored `research/scratch/espn/`. Used only for research checks (lineup shortfall, weekly spread); nothing in the pipeline reads it.

`data/archive/` cannot be regenerated: our projection snapshots (skill positions, and K and DEF in `streaming_snapshots`), Sleeper and outside projection snapshots, odds snapshots, season-odds history and daily player-status snapshots. `make refresh` copies it to `~/fantasy-app-backups` first; keep that folder out of any repository.

## Known limits

- Win-probability lineups usually match max-points lineups, and the app says so instead of inventing a swap.
- The trade acceptance figure is a share of past accepted trades that were as lopsided in market value, not a chance of acceptance: Sleeper keeps only completed trades (8 so far) and today's values.
- The drop-risk watch on the digest (This week) lists facts (snap share, market value, injury status); none is tested to predict a miss.
- Assumed, not measured: the weekly roster drift and the 50% Sleeper blend weight. The spread of season win totals is untested (Colgate is new this year; YinzBurgh's three ESPN seasons are loaded for weekly checks, but past mid-season forecasts were not kept). The weekly team-score range runs about 12% wide on 4 seasons of lineups; a correction missed the rule narrowly (t 1.86) and waits for more 2026 weeks.
- Defender injury curves reuse skill-player curves. Vacancy bumps are shared equally among a team's receivers or backs.
- No slot-matchup modeling: free data has no alignment.
- K and DEF use each team's own rostered unit projection in the season simulation, lineups and win probability (the league average where a team has none). Their spread is still league-wide, and past weeks in `calibration` use league means.
- Vegas lines exist only a few weeks ahead; later weeks use a neutral context.
- `data_api.py` is 571 lines. League inputs are cached per data version and cleared on each refresh. The cleanup follow-ups were issue #41 (closed).

## Documentation

- [docs/decisions.md](docs/decisions.md): every modeling decision, test and rejected idea with numbers.
- [docs/backlog.md](docs/backlog.md): story list, status and known gaps. [docs/one-pager.md](docs/one-pager.md): the short plan.
- [docs/spec/](docs/spec/): architecture, modeling, dashboard and data-source specs from the design phase (the backlog supersedes their story IDs).
- [CLAUDE.md](CLAUDE.md): conventions and gotchas for working in this repo with Claude Code.
- [research/README.md](research/README.md): index of the analysis scripts.

## Status

Built and used during the 2026 season. The React UI in `web/` is the only UI (the Streamlit app was removed in commit 0cd914c). Open work on GitHub: issue #40 (retest the Sleeper blend weight on clean snapshots, around week 11, which is also the trade deadline), #65 (phone access through `tailscale serve`), #66 (Streamlit removal, done in 0cd914c; the issue is still open), the #68 UI epic and #37 (post-MVP: FAAB, a 16-team FAAB league, dynasty, a draft assistant, an own model, a news model).
