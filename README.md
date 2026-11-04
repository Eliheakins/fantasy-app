# NFL Stat App — The Bridge

A local NFL stats workbench. Ask a question like "Mahomes passing yards and touchdowns in 2023" and get an answer and a table.

- **Backend:** FastAPI asks a local model to turn a question into stats and filters, and (locally) serves the static data files: the manifest, the player list and the play-by-play Parquet shards.
- **Frontend:** Vite + React. A small columnar engine (`frontend/src/shared/engine/`, hyparquet plus an evaluator for the SQL expressions in `metrics/metrics.json`) runs the queries in the browser, reading only the Parquet columns a query needs over HTTP range requests. A local model never writes queries and never sees player ids.

Everything runs on your machine. Data lives in `backend/data/`.

## How Ask works

1. Player names in the question are matched in the browser against the static player list (`players.json`). Namesakes are narrowed by the stats asked about, or you pick one.
2. Rules read the question first (`frontend/src/features/nlq/ruleParser.ts`): stats and their aliases, seasons, situations ("third down", "in the playoffs"), per game. They answer only when they understand every word, so a question with an unfamiliar word is not guessed at. Instant, free, and works with no model running.
3. Only a question the rules cannot fully read goes to the model: `POST /nlq/intent` sends it with the stat/filter catalog to a local model, which returns `{outcome: "query", intent: {stat_ids, filter_ids, granularity}}`, or `{outcome: "unsupported", reason}` when no stat can answer (salary, fantasy points, opinions). The reply is validated, with one retry on a bad reply. An answer from the model lists the words the rules did not recognise, and Ask says which path read each question. With no model server, Ask still answers what the rules can read and explains why for the rest.
4. The Explore query builder hands the stats and filters to the in-browser engine. The answer text is built from the result rows, not by the model.
5. Questions default to the regular season unless they mention the playoffs.
6. The answer is a link: the question and the query it became live in the URL, so reload, back/forward and sharing show the same result without asking the model again.

## Links

The query on Explore and Ask is in the URL as readable parameters, one `p`, `s` and `f` per value:

```
/explore?p=00-0033873&s=pass_yards&s=pass_sack_rate&f=season-2023&f=stype-reg&g=per_game&m=20
```

| Parameter | Meaning |
|-----------|---------|
| `p` | Player GSIS id (up to 5) |
| `s` | Stat id from `metrics/metrics.json` (up to 5) |
| `f` | Filter chip id, such as `season-2023`, `stype-reg`, `down-3` |
| `g` | `total`, `per_game` or `per_play` (default) |
| `m` | Minimum rows per player, 0 to 500 |
| `q` | Ask only: the question that produced the query |

Values the app does not recognise are ignored, so an old or edited link still opens. Explore and Ask each keep their own query; asking a question does not change Explore.

## Setup

Prerequisites: [uv](https://docs.astral.sh/uv/), Node.js 20+, and an Apple Silicon Mac for the MLX model server.

```bash
uv sync                       # backend dependencies (add --group llm for the model server)
cd frontend && npm install
```

### Data

```bash
uv run python backend/scripts/build_data.py            # 2021 through the current season
uv run python backend/scripts/build_data.py --years 2023,2024
```

This writes, into `backend/data/`:

| File | What it is |
|------|------------|
| `nfl_pbp_YYYY.parquet` | Play-by-play, one file per season, with participation and Next Gen Stats joined on |
| `player_game.parquet` | One row per player per game with official counting totals (tier 1) |
| `player_index.parquet` | One row per player; the build turns it into `players.json` |
| `players.json` | Player list the browser searches and matches names against (id, name, team, position) |
| `manifest.json` | What was built: seasons, files, rows, latest week, and when |

The season list comes from the data: a new season appears in the app as soon as its shard is built, with no code change. Missing values (Next Gen Stats cover only some plays, participation is not published until after a season ends) stay null, and the build prints how much of each column is missing. Pick up new games weekly with `uv run python backend/scripts/build_data.py --refresh`, which rebuilds only the current season and keeps the rest (`--years 2024,2025` rebuilds specific seasons). The API notices the new manifest without a restart, and the header shows how current the data is. If a brand-new season has no play-by-play published yet, build with `--years` up to the previous season.

### Two tiers

A query reads the small tier-1 table (`player_game.parquet`, built from nflverse weekly player stats: passing, rushing and receiving yards, touchdowns, receptions, yards after catch) when every selected stat is one of those counting stats and the only filters are season, season type and week. Those totals are the official ones; the play-level sums are not always (sack yards, for example). Per game divides by the games where the player had an attempt, carry or target, and per play by those attempts, carries or targets. Anything else (rates, EPA, Next Gen Stats, a down, quarter, home or away, or any other situational filter) reads the play-by-play shards for the seasons asked about, one column at a time. Which stats have a tier-1 column is the `player_game_column` field in `metrics/metrics.json`; a test checks each one against the recorded official totals.

`/health` reports `data_through` (for example `2026 week 8`) and the seasons loaded. The data files are static: the API's only dynamic endpoint is `POST /nlq/intent`. The browser reads `manifest.json`, `players.json` and the Parquet shards from one base URL, so they can be served from a CDN instead (see `VITE_DATA_BASE_URL` below).

## Run

Three terminals, from the repository root:

```bash
# 1. Local model (first run downloads about 8 GB)
uv run --group llm mlx_lm.server --model mlx-community/Qwen2.5-14B-Instruct-4bit --port 8080

# 2. API
uv run uvicorn nfl_stat.main:create_app --factory --port 8100

# 3. Frontend
cd frontend && npm run dev
```

Open `http://localhost:3000`. The API is `http://localhost:8100` (docs at `/docs`, health at `/health`). The API uses 8100 so it does not clash with other local servers on 8000.

The API pings the model every 20 seconds to keep its weights in memory. Without that, the first question after a pause took 20 to 40 seconds while macOS paged the model back in.

## Configuration

Optional, in the environment or a `.env` file at the repository root.

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BASE_URL` | `http://127.0.0.1:8080/v1` | OpenAI-compatible server (any local server works, for example LM Studio) |
| `LLM_MODEL` | `mlx-community/Qwen2.5-14B-Instruct-4bit` | Must match the model the server loaded |
| `LLM_TIMEOUT_SECONDS` | `120` | Per-request timeout |
| `VITE_API_BASE_URL` | `http://localhost:8100` | Where the browser finds `POST /nlq/intent` (frontend, set when starting Vite) |
| `VITE_DATA_BASE_URL` | `<VITE_API_BASE_URL>/data` | Where the browser finds `manifest.json`, `players.json` and the shards. Point it at a CDN and nothing else changes; the host must allow CORS for the page's origin and answer HTTP Range requests (expose `Content-Range`, `Content-Length` and `Accept-Ranges`). The API's own CORS list is only the local Vite origins |
| `PIPELINE_GC` | `1` | Set `0` to skip `gc.collect()` between seasons in the data build |
| `NFLVERSE_DOWNLOAD_BASE` | nflverse GitHub releases | Override the PBP download host |

## Tests

```bash
uv run pytest --cov           # backend unit and API tests
uv run pytest -m eval -s              # intent accuracy against the live local model (needs step 1 above)
cd frontend && npm test               # name matching, rules parser, answer text, catalog sync
cd frontend && npm run eval:rules     # how the rules parser scores on the eval questions (no model needed)
cd frontend && npm run export:catalog # refresh backend/tests/eval/catalog.json after changing stats or filters
uv run ruff check backend
```

## Measuring Ask

Two question sets with the expected stats, filters and granularity (or `unsupported`) live in `backend/tests/eval/`:

- `cases.json`: 44 questions, written alongside the model prompt and, later, the rules. Treat its scores as optimistic.
- `heldout.json`: 34 questions written **before** the rules parser, including traps that must not be answered (an unknown stat like "net yards per attempt", an opponent filter, a season outside the data, a leaderboard; the leaderboard trap is a trap for the model only, since the rules now answer it).

| | cases.json | heldout.json |
|---|---|---|
| Rules (`npm run eval:rules`) | 40/40 answerable correct, 0 wrong | 25/25 answerable correct (two more are deferred on purpose), 0 wrong; 1 trap refused, 7 handed to the model |
| Model (`uv run pytest -m eval -s`, Qwen2.5-14B-Instruct-4bit) | 42/44 | 25/34: answers all 7 traps instead of refusing them |

The model's refusal weakness is why an answer from the model lists the words the rules did not recognise. The model eval gates on `cases.json` only; improving its refusals is tracked in #9. `players.fixture.json` is a slice of `players.json` (the players named in the questions) so the rules eval runs in CI without built data.

## Layout

| Path | Role |
|------|------|
| `backend/nfl_stat/main.py` | App factory: routers, CORS for the local Vite port, static `/data` |
| `backend/nfl_stat/api/routers/` | `health`, `nlq` (intent). Everything else is static files under `/data` |
| `backend/nfl_stat/services/` | `nlq_intent` (prompt, validation, retry), `llm_client`, `llm_warmup`, catalogs |
| `backend/nfl_stat/pipeline/` | Data build from nflverse: play-by-play shards, the player-game table, the manifest (`build_data.py` is the entry point) |
| `frontend/src/features/nlq/` | Ask: name matching, hook, answer text, panel |
| `frontend/src/features/explore/` | Query builder and results canvas (also runs Ask's query) |
| `metrics/metrics.json` | The stat definitions: SQL, aliases, row filters and reference values. Read by the app and by the backend tests |
| `frontend/src/shared/config/` | Loads `metrics.json`; filter chips. The source for the model's catalog |

## Known limits

- Play-by-play has one or two fewer pass attempts than the official tables in some games (Mahomes 2023: one play in week 5 and one in week 11), so rates match the official figures to within about 0.5%, not exactly. Passing yards, touchdowns, receptions and rushing totals for the sampled player-seasons match exactly. Each metric's `reference_values` in `metrics/metrics.json` record the tolerance.
- Sack, penalty and no-play rows are pass plays in the data. Attempt-based stats (passing yards, passing TDs, completion %, interception rate) leave them out with a `play_filter`; edit that in `metrics/metrics.json` and run `uv run pytest`, which checks every metric against its reference values when data is built.
- Player search and name matching read `players.json`, built from nflverse rosters. A build over a few seasons keeps players from earlier builds (it merges, keeping each player's latest season), so retired and unsigned players stay findable.
- Per game divides by the games a player appeared in within the same season, season type, week and home/away filters. Situational filters (down, quarter, ...) do not shrink that count.
- The expression language in `metrics/metrics.json` and the filter chips is a SQL subset: `SUM/AVG/COUNT/NULLIF`, `CASE`, `CAST(.. AS DOUBLE)`, arithmetic, comparisons, `AND/OR/NOT`, `LIKE`. `frontend/src/shared/engine/expression.ts` names anything else it cannot run. There is no ad hoc SQL.
- "Min plays" counts the rows each stat uses: attempts for the filtered stats above, dropbacks (sacks included) for the rest. A passer near the threshold can show some stats and not others.
- Per-play values for EPA and WPA stats are per dropback; per-play passing yards, TDs, completion % and interception rate are per attempt.
- Leaderboards are read by the rules only ("who led the league in passing yards in 2023", "top 5 completion percentage in 2023"): the model is never asked, because it cannot rank. They show the top 10 unless the question says "top N"; per game and rate rankings need at least 100 plays. There is no way to rank lowest first from Ask, and no team or by-season/by-week queries yet. The URL carries them as `o=<stat>` (add `:asc` to reverse) and `n=<rows>`, and Explore shows but does not edit them.
- Name matching is exact on surnames and full names, so typos are not corrected.
- Receiving and rushing totals can differ slightly from official lines (play-by-play data).
- `mlx_lm.server` is not hardened for production; keep it on localhost.
