# web: React UI

Vite and React. Commands: `npm run typecheck` (`tsconfig.json` over every file, then `tsconfig.app.json` over app code alone, which does not see the vitest or jest-dom types), `npm run lint` (ESLint: typescript-eslint, the promise rules and the React hooks rules), `npm run format` / `format:check` (Prettier, print width 140), `npm run knip` (unused files, exports and dependencies), `npm test` (vitest, beside the code), `npm run types` (generated API types). Run from `web/`, or through `make check`.

## Layers and folders

- `architecture.test.ts` enforces the layers. Pages do not import other pages. Shared code (`lib/`, `components/`, `viz/`, `hooks/`, `api/`) imports no features or pages. `stat/` (engine, lib, config) imports no UI and no fantasy API, except the generated types in `api/schema`. `features/moves/trade/` does not import the rest of moves.
- Each tab has a folder under `features/`: `thisweek/{leagues,digest}`, `season/{outlook,league}`, `moves/{waivers,trade}`, `lineup/`, `players/`. Other features: `ask/`, `explore/`, `scorecard/`.
- Shared helpers: `lib/` (`week`, `scoreboard`, `digestTypes`, `outlookTypes`, `who`, `league.tsx`).
- `components/ui/`: primitives (button, input, textarea, select, tabs, toggle-group, tooltip, popover). The Radix-based ones use `radix-ui`. Popovers (the Find players chips) are Radix Popovers.
- Stat engine and kernel: `web/src/stat/`, see `stat/CLAUDE.md`.

## Tests

- `src/test/render.tsx`: `renderWithProviders(ui, { route, league, team, client })` wraps a fresh no-retry query client, then a `MemoryRouter` at `route`, `LeagueProvider` and `TeamProvider` as asked. A test with its own data router passes it as `ui` and leaves `route` out. `testQueryClient()` for `renderHook` wrappers.
- `src/test/fakeApi.ts` stubs the API strictly, like MSW's `onUnhandledRequest: "error"`. `stubApi(answer)`: the answer returns a reply (`okReply`, `errorReply`), a raw `Response`, or undefined for a request the test does not expect; that request gets a 500 and the global `afterEach` in `src/test/setup.ts` fails the test with "unexpected request: GET /api/...". `stubScoped(prefix, answer)` also answers the shell's own GETs (`/api/leagues`, `/api/status`, `/api/me/leagues`) with empty data; `stubRoutes(table)` answers by path. Calls are recorded as `{url, method, body}` from the client's `Request` (url relative to the page). Stub every request a test causes by name; never fall back to `okReply` for any url. Tests that mock `useLeagueApi` match on `leaguePath(route, query)` ("waivers?horizon=playoffs").
- Vitest runs with `unstubGlobals` and `restoreMocks`: before each test it undoes `vi.stubGlobal` and restores every `vi.spyOn`, so tests need no cleanup for those. Stub in `beforeEach` or the test, never at module level or in `beforeAll` (that is undone before the first test).

## Navigation

- `src/nav.ts` is the single source for the nav. It has five tabs, with no groups: This week `/`, Lineup, Moves, Season, Players. The top row shows from md up, and the bottom bar on phones. There is no More button or sheet (`AppShell.test.tsx` asserts that).
- `EXTRA_TITLES` in `nav.ts` names the other routes (`/ask`, `/model`, `/players/find`, `/players/compare`). Add a page in `nav.ts` and in `routes.tsx`.
- `lib/redirects.tsx` keeps old paths working, for example `/trades` to `/moves?view=trades` and `/explore` to `/players/find`.
- `components/layout/navLinks.ts`: every nav link keeps only `league`, `team` and `week`. Find players also gets the last Explore query (`stat/react/routeMemory.ts`).

## UI conventions

- A key number on a page (a change, or a percentage that answers the page) is an `Explain` or `ExplainDelta` from `src/viz`. Its text uses only values already in the response.
- Confidence words are only clear, lean and toss-up, via `Confidence`.
- Possessives go through `possessive()` in `src/lib/text.ts`.
- Filter labels the model reads are words, not symbols (the weather chips).
- My team's playoff state is `phaseOf(leagueRow)` (`features/effects/phase.ts`), from the server's `LeagueRow.team_phase`: regular -> season; playing, bye, consolation -> playoffs; eliminated -> out; champion, over -> over. With no `team_phase` the week decides (season or playoffs), never out. Out and over get no adds or trades; over gets no to-dos at all and shows `playoff_label` instead of "You are out of the playoffs". A consolation game keeps the hole to-dos.
- `routes.tsx` gives the AppShell route an `errorElement` (`components/layout/RouteError.tsx`): a page chunk that 404s after a redeploy shows "This page could not load" with a Reload button.

## Look F

- Stacking uses named layers from `@theme` in `src/index.css`, never raw `z-<number>`: `z-raised` 10 (sticky table cells, chart labels), `z-tab-bar` 10 (phone bottom bar, later in the DOM than the page), `z-banner` 20 (phone team banner), `z-header` 30 (sticky header from md), `z-overlay` 40 (dialog backdrop), `z-modal` 50 (dialog), `z-popover` 50 (Radix popover, select, `Explain`), `z-skip-link` 50. Popover equals modal on purpose: Radix portals mount last in `body`, so one opened from a dialog paints above it.
- Light only. Tokens are `--lf-*` in `src/index.css`. The spec and token table are in `docs/spec/dashboard.md` ("Look F tokens"). Use the tokens, not raw hex values. Charts take their colours from `src/viz/chartTheme.ts`.

## Fetching and the API

- Every `/api` call goes through the one typed client, `src/api/client.ts` (`openapi-fetch` over the generated `paths`). It adds `X-Requested-With: fantasy-app` to every request, which the API requires for non-GET calls. A call names the route template and its params, and the data type comes from the schema: never write `<T>` at a call site, and never build an `/api` url by hand.
- Use the `src/api/useEnvelope.ts` family: `useEnvelopeQuery(route, params | null, refetchMs?)` (null params keep it off; the viewed team is added as the `team` query param), `useEnvelopePolling`, `usePostEnvelope(key, route, {params, body} | null)` (simulation POSTs kept in the cache) and `useEnvelopeMutation(method, route, invalidates)` for writes (`mutate({params, body})`; its `error` and `isPending` replace hand-rolled busy and error state). League routes go through `lib/league.tsx`: `useLeagueApi(route, query?)` for the selected league, `useEachLeague` / `useLeagueQuery` for named leagues. A busy envelope polls and shows the elapsed time. Trade errors use `FailureNotice` (`features/moves/trade/`).
- GET keys are `["api", <resolved url>]`; build one with `apiKey(route, params)` (`useEnvelope.ts`), never by hand. `/api/me/leagues` and its key live in `features/leagues/myLeagues.ts`. `lib/session.tsx` alone keeps `sendJson`.
- Not through the client: `stat/lib/nlqApi.ts` (`/api/stat/nlq/intent`, through the stat kernel's zod-checked `requestJson`, which sets the header itself) and the stat shards and manifest.
- `src/api/queryClient.ts` `createAppQueryClient()` is the app's client: `["api", ...]` and `["post", ...]` queries retry once, every other query keeps react-query's default unless it sets its own. Test clients have no retries.
- The build puts react, react-dom, react-router and @tanstack/react-query (with their own dependencies) in a `vendor` chunk (`vite.config.ts`, Rolldown `output.codeSplitting.groups`; `manualChunks` is deprecated under Vite 8).

## Generated types and the checks that pin them

- `web/openapi.json` is generated: `uv run python -m fantasy.api --openapi > web/openapi.json`. Then `cd web && npm run types` writes `src/api/schema.d.ts`. Never edit either by hand.
- `tests/fantasy/api/test_api.py::test_openapi_snapshot_matches_the_app` pins `openapi.json` to the app.
- `src/api/schemaTypes.test.ts` pins `schema.d.ts` to `openapi.json`.
- `src/stat/lib/schemas/nlqIntent.ts` has compile-time checks that the Ask zod types equal the generated `QueryIntent`, `QueryOutcome` and `UnsupportedOutcome`. A pydantic change therefore breaks `tsc`.
