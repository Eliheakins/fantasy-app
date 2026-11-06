# Ask (`/ask`)

Ask answers an NFL question in plain language. `pages/Ask.tsx` has an Ask tab and a History tab; History has no nav entry. The model side (providers, Jev, eval) is in `src/nfl_stat/CLAUDE.md`.

## Entry and dispatch

- `components/layout/AskBox.tsx` in `TopBar` (input from md up, an icon button that reveals it on phones) navigates to `/ask?q=`, keeping only `league` and `team`. `useAsk` answers a `q` in the URL on arrival, when the URL holds no query.
- `paths/dispatch.ts` gives the question to each path in order. The first whose `read` matches answers: `startSitPath`, then `tradePath`, then `rulesPath`, then `modelPath`. The model is last, because it takes whatever names a player. `isStale` stops a slow answer from replacing one the user has moved past.

## Names

- `resolvePlayers.ts`: namesakes get the same choice buttons (`NlqPlayerPickers`). `resolveTeams.ts` does the team names.

## Rules parser

- `ruleParser.ts` is always tried first. It answers what it can, even with the intent endpoint down or no model server.
- `ruleParser.eval.test.ts` is the rules eval (`eval:rules` is gone). It pins the recorded numbers: cases 43/43 answerable correct and 0 wrong (40/40 before `league_pts`); heldout 26/26 correct, 0 wrong, 1 trap refused, 6 handed to the model. It reads `tests/stat/eval/`.
- A league stat has no position. The rules parser and `useAsk` ignore it when settling roles.

## Settling a stat to the subject

- `settleStats.ts` runs on every answer (`paths/queryStates.ts`), after the rules or the model. Generic words ("EPA", "success rate", "ADOT") name the first stat of a metric `family`, the passer's. A team gets the family's team stat; a player whose position has one main role (`MAIN_ROLE`: RB rusher, WR and TE receiver) gets that role's stat. A quarterback, players of mixed roles, and a stat named by role ("rushing EPA") are left as asked.
- Defense rankings flip `better` ("best defense" ranks the least allowed first).

## Model step

- `stat/lib/nlqApi.ts` posts to `/api/stat/nlq/intent` with `X-Requested-With: fantasy-app`. The model's reason and any model text are rendered as React text, never HTML.
- The intent cache (`intentCache.ts`) and the ask log (`askLog.ts`, `askLogStore.ts`) are in `localStorage`, so they are per origin. The old stat app's entries do not carry over.
- The model prompt does not list fantasy points as unsupported. League points are a catalog metric (`web/src/stat/CLAUDE.md`).
- Refresh the model catalog fixture with `UPDATE_CATALOG=1 npx vitest run nlqCatalog.test.ts` in `web/` (the test is `web/src/stat/lib/nlqCatalog.test.ts`).

## Start/sit

- Read by `readStartSit` (`startSit.ts`, `startSitPath.ts`) before the intent flow. The model prompt and catalog are untouched, and the model is never asked. Patterns: "start A or B", "should I start/sit A or B", "A or B this week". Words after a name ("Kelce or Kittle receptions this week") leave the question to the stat path.
- Both names resolve with `resolvePlayers` to outcome `start_sit` with two gsis ids. `StartSitAnswer.tsx` renders the answer.
- The answer reads `GET /api/leagues/{league}/lineup` (current week, viewed team). Its projections with p10/p90 come from `_engine._week_values`. No new route: no existing route gives the win-probability effect of one pairwise swap, and win probability is a whole-lineup job.
- The choice is the Lineup page's own `recommended` flag. Exactly one: "Start A over B". Both: "Your lineup starts both". Neither: "benches both", plus who projects more. Never a projection comparison of its own.
- The gap is shown as projected points, with no clear/lean/toss-up tag, since that needs the share of simulations. The Lineup link carries win probability.
- A player not on that roster, or locked, gets a notice instead of a recommendation.
- Logged as outcome kind `start_sit` (text only). History reopens it by `q`.

## Trades

- Read by rules alone after start/sit and before the intent flow (`tradeAsk.ts`, `tradePath.ts`). Patterns: "trade A for B", "should I trade A for B", "A for B trade", with up to two names per side joined by `and`, `&` or a comma. Anything else ("Kelce or Kittle", stat comparisons) goes to its own path. Names resolve as in start/sit.
- `planTrade` takes the give side as the viewed team's players, and the get side as one other team's players from `GET /api/leagues/{league}/owners` (`is_mine`, `owner`). The partner is the owners row's `roster_id`. It was added to `player_owners` and `OwnerRow` because team names can repeat. There is no trade-partners call.
- It posts `{partner_roster_id, give_ids, get_ids}` to `/trades/evaluate` with `usePostEnvelope`, and renders `TradeAnswer.tsx` with `TradeResult` (`features/moves/trade/TradeResult.tsx`). One sentence above the result (`tradeSummary`, same rounding as the result, no verdict) gives the change in the viewed team's playoff and title odds, in points.
- A kicker or defense (no owners row, not in the stat data) hands off as unsupported, not as a free agent.
- Several owners, a free agent (no owners row), a get player already on the viewed team, or a give player not on it: hand off with a message and a link to `/trades`, keeping `league` and `team`. Nothing is guessed.
- The evaluate response has no Monte Carlo error (only Find trades has `se_title`), so none is shown.
- Logged as outcome kind `trade` (text only). History reopens it by `q`.
