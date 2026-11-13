import { apiKey } from "@/api/useEnvelope";

/** The account's added leagues: read by the list and the welcome dialog, refetched after an add, a remove or a team change. */
export const MY_LEAGUES = "/api/me/leagues";
export const MY_LEAGUES_KEY = apiKey(MY_LEAGUES);
