# web: React UI

Vite and React. Commands: `npm run typecheck`, `npm test` (vitest, beside the code), `npm run types` (generated API types). Run from `web/`, or through `make check`.

## Layers and folders

- `architecture.test.ts` enforces the layers. Pages do not import other pages. `lib/` and `components/` import no features or pages. `stat/` (engine, lib, config) imports no UI and no fantasy API, except the generated types in `api/schema`. `features/moves/trade/` does not import the rest of moves.
- Each tab has a folder under `features/`: `thisweek/{leagues,digest}`, `season/{outlook,league}`, `moves/{waivers,trade}`, `lineup/`, `players/`. Other features: `ask/`, `explore/`, `scorecard/`.
- Shared helpers: `lib/` (`week`, `scoreboard`, `digestTypes`, `outlookTypes`, `who`, `league.tsx`).
- `components/ui/`: primitives (button, input, textarea, select, tabs, toggle-group, tooltip, accordion). The Radix-based ones use `radix-ui`. Dialogs (the phone builder) are Radix Dialogs.
- Stat engine and kernel: `web/src/stat/`, see `stat/CLAUDE.md`.

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

## Look F

- Light only. Tokens are `--lf-*` in `src/index.css`. The spec and token table are in `docs/spec/dashboard.md` ("Look F tokens"). Use the tokens, not raw hex values. Charts take their colours from `src/viz/chartTheme.ts`.

## Fetching and the API

- `src/api/envelope.ts` `fetchEnvelope` adds `X-Requested-With: fantasy-app` to every request, which the API requires for non-GET calls.
- Use the `src/api/useEnvelope.ts` family: `useEnvelopeQuery`, `useEnvelopePolling`, `usePostEnvelope` (for POSTs) and `useEnvelopeMutation`. A busy envelope polls and shows the elapsed time. Trade errors use `FailureNotice` (`features/moves/trade/`).
- `stat/lib/nlqApi.ts` sets the header itself.

## Generated types and the checks that pin them

- `web/openapi.json` is generated: `uv run python -m fantasy.api --openapi > web/openapi.json`. Then `cd web && npm run types` writes `src/api/schema.d.ts`. Never edit either by hand.
- `tests/fantasy/api/test_api.py::test_openapi_snapshot_matches_the_app` pins `openapi.json` to the app.
- `src/api/schemaTypes.test.ts` pins `schema.d.ts` to `openapi.json`.
- `src/stat/lib/schemas/nlqIntent.ts` has compile-time checks that the Ask zod types equal the generated `QueryIntent`, `QueryOutcome` and `UnsupportedOutcome`. A pydantic change therefore breaks `tsc`.
