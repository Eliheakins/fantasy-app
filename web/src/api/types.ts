// Friendly aliases over src/api/schema.d.ts, which `npm run types` generates from openapi.json.
import type { components } from "./schema";

type Schemas = components["schemas"];

export type ApiErrorBody = Schemas["ApiError"];
export type EnvelopeStatus = Schemas["Envelope_StatusData_"]["status"];
export const ENVELOPE_STATUSES: readonly EnvelopeStatus[] = ["ok", "running", "error"];

/** The real envelope: all four keys are always present. */
export type Envelope<T> = {
  status: EnvelopeStatus;
  data: T | null;
  error: ApiErrorBody | null;
  started_at: string | null;
};

export type League = Schemas["LeagueRow"];
export type Status = Schemas["StatusData"];
/** The signed-in account: `/api/auth/me`, and what sign-in and invite redemption return. */
export type Me = Schemas["Me"];
/** The admin page: `/api/admin/*`. */
export type AdminAccount = Schemas["AccountRow"];
export type InviteCreated = Schemas["InviteCreated"];
export type RefreshAdmin = Schemas["RefreshAdmin"];
export type AdminRun = Schemas["RunRow"];
/** Adding Sleeper leagues by username: `/api/me/*`. */
export type MyLeague = Schemas["MyLeague"];
export type SleeperLookup = Schemas["Lookup"];
export type SleeperLeague = Schemas["SleeperLeague"];
/** `/api/stat/health`: a plain body, not the envelope. */
export type StatHealth = Schemas["HealthResponse"];
