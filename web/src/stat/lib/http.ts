import { z } from "zod";

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

/** URLs are usually relative to the page, so resolve them before taking the origin (outside a browser there is no page, so absolute URLs stand alone). */
const originOf = (url: string) => new URL(url, globalThis.location?.href).origin;

// `detail` is FastAPI's own shape; `error.message` is the fantasy envelope the host app now sends.
const errorBodySchema = z.object({
  detail: z.unknown().optional(), // zod 4.6+ requires an unknown key unless it is optional
  error: z.object({ message: z.string() }).nullish().catch(null),
});

/** FastAPI sends `detail` as a string, or as a list of validation errors with a `msg` each. */
function describeDetail(detail: unknown): string | null {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail.flatMap((item: unknown) => {
      const parsed = z.object({ msg: z.string() }).safeParse(item);
      return parsed.success ? [parsed.data.msg] : [];
    });
    return messages.length > 0 ? messages.join("; ") : null;
  }
  return null;
}

async function errorDetail(res: Response): Promise<string | null> {
  try {
    const parsed = errorBodySchema.safeParse(await res.json());
    if (!parsed.success) return null;
    return describeDetail(parsed.data.detail) ?? parsed.data.error?.message ?? null;
  } catch {
    // The body was not JSON; the caller falls back to the status.
    return null;
  }
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
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw e;
    }
    throw new Error(
      `${capitalize(what)} is not reachable at ${originOf(url)}. ${unreachableHint}`,
    );
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
    throw new Error(`The response for ${what} was not JSON. Is the server at ${originOf(url)} the right one?`);
  }

  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    const where = issue?.path.join(".") || "(root)";
    throw new Error(
      oneLine(
        `${capitalize(what)} has an unexpected shape at "${where}": ${issue?.message ?? "invalid"}. ${shapeHint}`,
      ),
    );
  }
  return parsed.data;
}
