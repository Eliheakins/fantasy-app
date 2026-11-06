import { type FantasyRoute, readFantasyRoute } from "../fantasyRoute";
import type { AskPath } from "./types";

/** Injuries, projections, waivers and byes: a link to the page that has them, read by rules alone (no model). */
export const routePath: AskPath<FantasyRoute> = {
  id: "route",
  read: (input) => readFantasyRoute(input.question, input.dictionary),
  answer: (route, { question }, actions) => actions.showRoute(route, question),
};
