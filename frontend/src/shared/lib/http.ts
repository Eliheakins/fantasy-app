import type { z } from "zod";

export interface RequestJsonOptions {
  /** What is being fetched, as it reads in a sentence: "the data manifest". */
  what: string;
  /** How to fix an unreachable server. */
  unreachableHint: string;
  notFoundHint?: string;
  shapeHint?: string;
  init?: RequestInit;
}

const capitalize = (text: string) => text.charAt(0).toUpperCase() + text.slice(1);
const oneLine = (text: string) => text.replace(/\s+/g, " ").trim();

async function errorDetail(res: Response): Promise<string | null> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (body.detail !== undefined && body.detail !== null) {
      return JSON.stringify(body.detail);
    }
  } catch {
    // The body was not JSON; the caller falls back to the status.
  }
  return null;
}

/**
 * Fetches JSON and checks it against a schema. Every failure becomes one readable sentence that
 * says what failed, where, and what to do, rather than "Failed to fetch" or a raw parse error.
 */
export async function requestJson<S extends z.ZodType>(
  url: string,
  schema: S,
  options: RequestJsonOptions,
): Promise<z.output<S>> {
  const { what, unreachableHint, notFoundHint = "", shapeHint = "", init } = options;

  let res: Response;
  try {
    res = await fetch(url, init);
  } catch {
    throw new Error(`${capitalize(what)} is not reachable at ${new URL(url).origin}. ${unreachableHint}`);
  }

  if (res.status === 404) {
    throw new Error(oneLine(`${capitalize(what)} was not found at ${url}. ${notFoundHint}`));
  }
  if (!res.ok) {
    throw new Error((await errorDetail(res)) ?? `${capitalize(what)} request failed (${res.status}).`);
  }

  let body: unknown;
  try {
    body = await res.json();
  } catch {
    throw new Error(`The response for ${what} was not JSON. Is the server at ${new URL(url).origin} the right one?`);
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    const where = issue?.path.join(".") || "(root)";
    throw new Error(
      oneLine(`${capitalize(what)} has an unexpected shape at "${where}": ${issue?.message ?? "invalid"}. ${shapeHint}`),
    );
  }
  return parsed.data;
}
