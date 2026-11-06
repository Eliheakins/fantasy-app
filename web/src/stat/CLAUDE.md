# web/src/stat: query engine and kernel

The stat code in the browser. The engine runs queries on Parquet shards from `/api/stat/data/`. No UI here, except `react/`, the one part allowed React.

## Layout

- `engine/`: `statQuery.ts` (`runUnordered`, the play-stat path), `playerGameQuery.ts`, `leaguePointsQuery.ts`, `columns.ts`, `expression.ts`, `parquetColumns.ts`.
- `lib/`: URLs, schemas (`schemas/`), manifest and player loading, `nlqApi.ts` and `nlqCatalog.ts` (Ask), `queryBuilder.ts` (`statLabel`).
- `config/`: the stat dictionary, built from `metrics/metrics.json`.
- `react/` (the kernel): `manifest.tsx` (`ManifestProvider`, `useManifest`), `useQueryState.ts` (keeps `league` and `team` when it writes), `filterChipGroups.ts`, `routeMemory.ts` (the last Explore query without `league` and `team`), `useLeaguePoints.ts`.
- Base URLs are fixed at `/api/stat` and `/api/stat/data`. The manifest's seasons are passed in as arguments. There is no store.

## Roles, families and team stats

- A play stat counts the plays of one role (`player_role`: passer, rusher or receiver) and play type. Efficiency is role-aware: `eff_*` and `pass_adot` are the passer's, `rush_epa`/`rush_success` the rusher's carries, `rec_epa`/`rec_success`/`rec_adot` the receiver's targets.
- `team_only` stats (`team_epa`, `team_success`) count every pass and run play by `posteam` or `defteam`, whoever had the ball; their role is a placeholder and a player query on them throws.
- `family` groups the versions of one stat; the first in `metrics.json` is the default. `familyMember` and `familyDefault` in `config/statDictionary.ts` pick among them (Ask's `settleStats`).

## Derived stats

- `source: "derived"` metrics have a `formula` over other metrics' totals instead of play SQL (`engine/derivedQuery.ts`, joined in `runPlayAndDerived`). In a formula, a metric id is that stat's total for the row (0 when the player has none of its plays), `team__<id>` the team's total of a counting stat in the games the player played (for the team he played for in each, under the same chips), and `games` his games played. A derived count per game divides by `games`; a derived rate is used as written, and its `volume` formula is what the minimum plays compares against.
- Scrimmage yards, touches, total TDs, fumbles lost, passer rating, standard/half/full PPR points and the shares (target, air yards, WOPR, opportunity) are derived. Shares are refused for teams.
- `hidden` metrics are formula parts only: not in the picker (`getStatsByCategory`), the model catalog or the rules.
- A counting stat written as one `SUM(<row expression>)` gets per game and per play (`summedExpression`).

## Opponents, home and away, positions

- The `opponent` chips (`opp-XXX`, `defteam = 'XXX'`) are a game-scope group, read in code by Ask and left out of the model catalog (`CODE_READ_GROUP_IDS`).
- Split `location` gives one row per player at home and away (`posteam_type`); the player-game table has no such column, so it runs on the play-by-play.
- `StatQueryParams.position` and `rookie` narrow players through the player index (`playerIndex`, `engine/playerFilters.ts`): a rookie in season S has latest season minus years of experience equal to S (S is the one season chip on, else the latest season). They narrow `playerSet` and ignore teams.

## Weeks and last N games

- The `week_number` chips (`wk-1` to `wk-22`) pick single weeks; several make a range. They are a game-scope group, and the player-game table and league points answer them. They are left out of the model catalog (`CODE_READ_GROUP_IDS`): Ask reads weeks in code.
- `StatQueryParams.lastGames` (URL `last`) keeps each player's or team's latest N games by season then week, within the season, season-type and week chips (`engine/lastGames.ts`), on all three paths.

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
