# web/src/stat: query engine and kernel

The stat code in the browser. The engine runs queries on Parquet shards from `/api/stat/data/`. No UI here, except `react/`, the one part allowed React.

## Layout

- `engine/`: `statQuery.ts` (`runUnordered`, the play-stat path), `playerGameQuery.ts`, `leaguePointsQuery.ts`, `columns.ts`, `expression.ts`, `parquetColumns.ts`.
- `lib/`: URLs, schemas (`schemas/`), manifest and player loading, `nlqApi.ts` and `nlqCatalog.ts` (Ask), `queryBuilder.ts` (`statLabel`).
- `config/`: the stat dictionary, built from `metrics/metrics.json`.
- `react/` (the kernel): `manifest.tsx` (`ManifestProvider`, `useManifest`), `useQueryState.ts` (keeps `league` and `team` when it writes), `filterChipGroups.ts`, `routeMemory.ts` (the last Explore query without `league` and `team`), `useLeaguePoints.ts`.
- Base URLs are fixed at `/api/stat` and `/api/stat/data`. The manifest's seasons are passed in as arguments. There is no store.

## Engine tests

Engine tests that read shards (`referenceValues`, `parquetColumns`) skip until `make stat-data` has built `data/stat/`.

## League points (`league_pts`)

- One catalog metric with `source: "league"`. It has no play SQL, role or filter. Both metric schemas allow that only for league metrics.
- It stays generic: no league id or name reaches the model. The UI names the selected league on the label (`statLabel`, `useLeagueName` in `lib/league.tsx`). The catalog and model request stay generic.
- `useLeaguePoints` calls `GET /api/leagues/{league}/player-points?season=`. It sends one request per season. With pinned players it asks per player (`gsis_id`). It fetches the chosen seasons (every season for a split by season, otherwise only the latest, with a notice). It caches for 5 minutes, does not refetch on focus, and has no manifest `built_at` in its key, because only `make refresh` changes `player_points`. Rows go in as `StatQueryParams.leaguePoints`.
- `engine/leaguePointsQuery.ts` answers league stats: total, per game over weeks with a points row, per play (as per game), ranking, split, season and week chips. `runUnordered` left-joins those rows onto any play stats. Play rows are the base, so min plays and role still apply.
- A playoffs-only chip gets a "regular season only" notice. A play-level chip gives no rows and a `QueryResult.notices` entry. No league is an error that says to pick one. Team rows are refused. Min plays does not apply.
- A league stat has no position. The rules parser and `useAsk` ignore it when settling roles.

## League filter, engine side

- `StatQueryParams.playerSet` holds ids plus `exclude`. Free agents are everyone not rostered. It applies in `wantedPlayers` before ranking, and it narrows pinned players too.
- The UI control and the URL key are in `web/src/features/explore/CLAUDE.md`.

## Privacy

- League data never goes under `data/stat`. The stat engine reads only nflverse shards.
