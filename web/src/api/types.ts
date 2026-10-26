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
