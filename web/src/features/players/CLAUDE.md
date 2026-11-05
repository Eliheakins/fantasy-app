# Player page (`/players/:gsisId`) and compare

## Page

- `pages/Player.tsx`. Player names anywhere (`PlayerLink`) are router links to it. There is no side sheet.
- `usePlayer` reads position and team from the players file.
- The weekly game log (`useGameLog`, `PlayerGameLog.tsx`): the manifest, then `runStatQuery` by week for the regular season, with the per-position stats from `lib/statLink.ts`, plus the NFL team from the players file. It is joined by week with this league's points from `GET /api/leagues/{league}/player-points?gsis_id=&season=` (`_market.player_points`, regular season). `player-weeks` (next-week projections) is not used. Owner comes from `/owners`.
- "Open in Explore" uses the `statLink` URL from `lib/statLink.ts`, which keeps `league` and `team`.

## Sections

- `PlayerSections.tsx` and `profile.ts` (`useProfile.ts`): next game range, rest of season over replacement, role sparklines, why, injury, market value and owner.
- They read `GET /api/leagues/{league}/players/{gsis_id}/profile` (`data_api.player_profile`, `_profile.py`). This is display only.
- The old rule of no projections on this page was reversed by the redesign plan.
- Failures are isolated. An engine or manifest failure shows a Callout and keeps league points. A points failure keeps the game log.

## Compare

- `/players/compare?p=` (`pages/PlayersCompare.tsx`) shows two or three players side by side.
