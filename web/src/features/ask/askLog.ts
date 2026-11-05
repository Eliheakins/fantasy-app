import { z } from "zod";

import { queryIntentSchema } from "@/stat/lib/schemas/nlqIntent";
import type { GranularityMode } from "@/stat/types/queryBuilder";

/**
 * A local record of every Ask: what was asked, how it was read, and what the user changed. It lives
 * in this browser only (nothing is sent anywhere) and feeds the eval set through `toEvalCases`.
 */

export const MAX_LOG_ENTRIES = 200;
const STORAGE_KEY = "bridge.askLog.v1";

const loggedQuerySchema = z.object({
  players: z.array(z.string()),
  stats: z.array(z.string()),
  filters: z.array(z.string()),
  granularity: queryIntentSchema.shape.granularity,
  order: z.object({ metric: z.string(), direction: z.enum(["asc", "desc"]) }).nullable(),
  limit: z.number().int().nullable(),
  // Logs written before splits existed have no split.
  split: z.enum(["season", "week"]).nullable().default(null),
  subject: z.enum(["players", "teams"]).default("players"),
  teams: z.array(z.string()).default([]),
  side: z.enum(["offense", "defense"]).default("offense"),
});

const entrySchema = z.object({
  id: z.string().min(1),
  at: z.string(),
  question: z.string(),
  path: z.enum(["rules", "model", "saved", "none"]),
  outcome: z.discriminatedUnion("kind", [
    z.object({ kind: z.literal("answered"), query: loggedQuerySchema }),
    z.object({ kind: z.literal("message"), text: z.string() }),
    // A start/sit answer comes from the lineup, so there is no query to keep, only what it was about.
    z.object({ kind: z.literal("start_sit"), text: z.string() }),
  ]),
  corrected: loggedQuerySchema.nullable(),
});

export type LoggedQuery = z.infer<typeof loggedQuerySchema>;
export type AskLogEntry = z.infer<typeof entrySchema>;
export type StorageLike = Pick<Storage, "getItem" | "setItem">;

/** The eval files' case shape (`backend/tests/eval/*.json`). */
export interface EvalCaseDraft {
  q: string;
  stats: string[];
  filters: string[];
  granularity: GranularityMode;
}

export const appendEntry = (entries: readonly AskLogEntry[], entry: AskLogEntry): AskLogEntry[] =>
  [entry, ...entries].slice(0, MAX_LOG_ENTRIES);

const sameQuery = (a: LoggedQuery, b: LoggedQuery) => JSON.stringify(a) === JSON.stringify(b);

/** Records what the query became after the user edited the answer; putting it back clears the correction. */
export function recordCorrection(entries: readonly AskLogEntry[], id: string, query: LoggedQuery): AskLogEntry[] {
  return entries.map((e) =>
    e.id === id && e.outcome.kind === "answered"
      ? { ...e, corrected: sameQuery(e.outcome.query, query) ? null : query }
      : e,
  );
}

/**
 * True when the query on screen (`key`) is an edit not yet logged for entry `id`. `last` is the last
 * edit logged in this session; it may belong to an earlier entry, so it only counts for the same id.
 */
export function isNewEdit(
  last: { id: string; key: string } | null,
  id: string,
  answeredKey: string,
  key: string,
): boolean {
  return last?.id === id ? last.key !== key : key !== answeredKey;
}

export function loadLog(storage: StorageLike): AskLogEntry[] {
  try {
    const raw: unknown = JSON.parse(storage.getItem(STORAGE_KEY) ?? "[]");
    if (!Array.isArray(raw)) {
      return [];
    }
    return raw.flatMap((item) => {
      const parsed = entrySchema.safeParse(item);
      return parsed.success ? [parsed.data] : [];
    });
  } catch {
    // A missing, blocked or damaged store means an empty history, never a broken page.
    return [];
  }
}

export function saveLog(storage: StorageLike, entries: readonly AskLogEntry[]): void {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // Storage can be full or blocked (private windows); the log is a convenience, so drop it quietly.
  }
}

/** Corrected answers as eval cases: the user's fix is the expected answer. Leaderboards are left out. */
export function toEvalCases(entries: readonly AskLogEntry[]): EvalCaseDraft[] {
  return entries.flatMap((e) =>
    e.corrected && e.corrected.subject === "players" && e.corrected.order === null && e.corrected.limit === null
      ? [
          {
            q: e.question,
            stats: e.corrected.stats,
            filters: e.corrected.filters,
            granularity: e.corrected.granularity,
          },
        ]
      : [],
  );
}
