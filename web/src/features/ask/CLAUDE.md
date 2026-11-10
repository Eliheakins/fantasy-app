# Ask (`/ask`)

Ask answers an NFL question in plain language. `pages/Ask.tsx` has an Ask tab and a History tab; History has no nav entry. The model side (providers, Jev, eval) is in `src/nfl_stat/CLAUDE.md`.

## Entry and dispatch

- `components/layout/AskBox.tsx` in `TopBar` (input from md up, an icon button that reveals it on phones) navigates to `/ask?q=`, keeping only `league` and `team`. `useAsk` answers a `q` in the URL on arrival, when the URL holds no query.
- `paths/dispatch.ts` gives the question to each path in order. The first whose `read` matches answers: `startSitPath`, then `tradePath`, then `routePath`, then `rulesPath`, then `modelPath`. The model is last, because it takes whatever the others leave. `isStale` stops a slow answer from replacing one the user has moved past.
- `rulesPath` takes a no-player question only when the rules fully read it (a ranking or a team question) or refuse it with certainty. Otherwise the model reads it, and `showModelRanking` makes a leaderboard when the words ask for a ranking or the model set `ranking`; with neither, it names no one and is refused.

## Fantasy routes

- `fantasyRoute.ts` / `paths/routePath.ts` (after trades, before the stat paths, rules only): waivers, pick-ups and drops link to Moves (free agents); one player's injury, projection, rest of season or outlook to his player page; projections with no player, byes and this week's opponent to Lineup; strength of schedule is said to be missing. `RouteAnswer.tsx` shows the link (keeping `league` and `team`). The model is never asked, so no league data reaches it. Logged as a message.

## Opponents, contrasts and stat lines

- `opponents.ts` reads a team after "against", "vs", "versus" or "facing" as an `opp-` chip, next to a player or another team. With no player and only that team, the team stays the subject ("passing yards against the Chiefs" is the Chiefs' defense). Opponents are cut from the model's text (`modelText`) and added back in `timeOf`.
- "2023 vs 2024" splits by season and "home vs away" by `location`; other contrasts are refused. "X stats" / "stat line" gives the position's usual counts (`STAT_LINES` in `ruleParser.ts`).

## Rankings

- `ranking.ts` reads a ranking the same way on both paths: direction (`better`, flipped for a defense), "top N", "min N carries/targets/attempts" (the unit must be the ranked stat's role), "in a single game" (split by week). Default floor: 100 plays for a rate, per-game or fewest-first ranking, 10 for a weekly one, none for most-first totals and teams.
- `readWho` reads position nouns (QB, RB, WR, TE in their usual words), "rookie" and role nouns ("rushers"). Position and rookie become `QueryState.position` / `rookie`; a generic stat settles to the position's own; a role noun must agree with the ranked stat or picks its family member.
- `ruleEval.ts`: a case's `rules_reads` is what the rules must read where the model alone must refuse (opponents are read in code before the model is asked).

## Names

- `resolvePlayers.ts`: namesakes get the same choice buttons (`NlqPlayerPickers`). `resolveTeams.ts` does the team names.

## Rules parser

- `ruleParser.ts` is always tried first. It answers what it can, even with the intent endpoint down or no model server.
- `ruleParser.eval.test.ts` is the rules eval (`eval:rules` is gone). It pins the recorded numbers: cases 43/43 answerable correct and 0 wrong (40/40 before `league_pts`); heldout 28/28 correct, 0 wrong, 1 trap refused, the opponent trap read by the rules (`rules_reads`), 4 handed to the model (25/25 and 7 before the 2026-11-06 expansion relabelled four cases; see `docs/decisions.md`). It reads `tests/stat/eval/`.
- A league stat has no position. The rules parser and `useAsk` ignore it when settling roles.

## Time words and the default season

- `timeWords.ts` reads relative time in code: this/last season, two seasons ago, week N, week ranges, since week N, this/last week (the latest week in the manifest), last N games, career. The rules mark the words read; the model is sent the question without them (`readTime(...).rest`), and `withTime` puts the code's reading in place of the model's.
- `paths/queryStates.ts` `timeOf` builds the answer's time: the code-read filters, `lastGames`, and the current season when none is named, with a note (`AskActions.answer` takes `notes`, shown under the answer). Career, a split by season, and only-rare situations (playoffs, wind, cold) keep every season.

## Settling a stat to the subject

- `settleStats.ts` runs on every answer (`paths/queryStates.ts`), after the rules or the model. Generic words ("EPA", "success rate", "ADOT") name the first stat of a metric `family`, the passer's. A team gets the family's team stat; a player whose position has one main role (`MAIN_ROLE`: RB rusher, WR and TE receiver) gets that role's stat. A quarterback, players of mixed roles, and a stat named by role ("rushing EPA") are left as asked.
- Defense rankings flip `better` ("best defense" ranks the least allowed first).

## Model step

- `stat/lib/nlqApi.ts` posts to `/api/stat/nlq/intent` with `X-Requested-With: fantasy-app`. The model's reason and any model text are rendered as React text, never HTML.
- The intent cache (`intentCache.ts`) and the ask log (`askLog.ts`, `askLogStore.ts`) are in `localStorage`, so they are per origin. The old stat app's entries do not carry over. When a different account signs in on the same browser, `lib/session.tsx` (`scopeStorageTo`) clears every `fantasy.*` and `bridge.*` key; a browser with no `fantasy.account` yet adopts the account and keeps its keys.
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
