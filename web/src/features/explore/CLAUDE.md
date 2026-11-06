# Find players (`/players/find`)

Explore is the Find players page. `/explore` redirects here (`lib/redirects.tsx`). The engine and kernel are in `web/src/stat/`.

## Page and loading

- `pages/Explore.tsx` wraps the page in `ManifestProvider` (`stat/react/manifest.tsx`), which queries `/api/stat/data/manifest.json`. Loading and errors show in the content area, with a retry.
- Pieces: `QueryBuilderPanel`, `ExploreResultsCanvas` (shows `QueryResult.notices`), `PinnedPlayersBar`, `usePinnedPlayers`, `useExploreQueryExecution`, `StatDictionaryPanel`, and `ExploreMobileBuilderDrawer` (the phone builder, a full-height Radix Dialog sheet).
- Saved searches: `savedSearchStore.ts`, in `localStorage`, so they are per origin.

## URL keys

- The query lives in the URL under these keys (`web/src/stat/lib/queryUrl.ts`): `p` players, `s` stats, `f` filters, `g` granularity, `m` min plays, `o` order, `n` limit, `by` split, `who` subject, `t` teams, `side`, `lg` league filter, `last` last N games (set by Ask; no Explore control, shown in the query details).
- Explore's keys never go on other links. `useQueryState` keeps `league` and `team` when it writes.

## League filter (`lg`)

- `lg=mine|rostered|fa`. Absent means all players, and bad values are ignored.
- It restricts player rows to today's rosters of the selected league and the viewed team. Data comes from `GET /api/leagues/{league}/owners` (`data_api.player_owners`: `{rows: [{gsis_id, owner, is_mine}], unmatched}`).
- The endpoint returns every rostered player in the league who has an nflverse id. Free agents have no row.
- `unmatched` counts rostered QB, RB, WR and TE with no nflverse id. The control shows that count, because those players would otherwise read as free agents.
- `?team=` makes that team "mine". Outlook was not used: it skips unprojected and low-projection players, and calls my team "You".
- Teams ignore the filter. The control is hidden for teams and with no league, and an `lg` left in the URL in those cases is dropped.
- A query with `lg` waits for the rosters rather than show unrestricted rows. A result is shown only for the league, viewed team and rosters it was computed for.
- Result rows show the owner in `text-muted`.
- The engine side (`playerSet`) is in `web/src/stat/CLAUDE.md`.
