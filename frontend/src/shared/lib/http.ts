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

const errorBodySchema = z.object({ detail: z.unknown() });

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
    return parsed.success ? describeDetail(parsed.data.detail) : null;
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
    // The browser hides whether this was a refused connection, CORS or mixed content.
    throw new Error(
      `${capitalize(what)} is not reachable at ${new URL(url).origin}, or the browser blocked the request (CORS). ${unreachableHint}`,
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
