import createClient, { createFinalURL, createQuerySerializer, defaultPathSerializer } from "openapi-fetch";
import type { paths } from "./schema";

/**
 * The one typed client over the generated `paths` (`schema.d.ts`). Call sites name a route template and its
 * params; the response type comes from the schema. The envelope handling sits on top, in `envelope.ts`.
 */

export type Method = "get" | "post" | "put" | "delete";
type Operation<P extends keyof paths, M extends Method> = NonNullable<paths[P][M]>;
type OkJson<O> = O extends { responses: { 200: { content: { "application/json": infer J } } } } ? J : never;

/** The routes that answer `M` with the envelope ({status, data, error, started_at}). */
export type Route<M extends Method> = {
  [P in keyof paths]: [OkJson<Operation<P, M>>] extends [never]
    ? never
    : OkJson<Operation<P, M>> extends { status: unknown; data: unknown }
      ? P
      : never;
}[keyof paths];

/** A route's params as the schema names them: path and query (header and cookie are never used). Not a `Pick`:
 * picking literal keys from a generic type makes them required, so a route without params would need some. */
export type Params<P extends keyof paths, M extends Method> = Operation<P, M>["parameters"];

/** The `data` of a route's ok envelope. */
export type ApiData<P extends keyof paths, M extends Method> = OkJson<Operation<P, M>> extends { data: infer D } ? NonNullable<D> : never;

type Body<P extends keyof paths, M extends Method> =
  Operation<P, M> extends { requestBody?: never }
    ? never
    : NonNullable<Operation<P, M>["requestBody"]> extends { content: { "application/json": infer B } }
      ? B
      : never;

/** The empty object type: `Empty extends T` holds when nothing in T is required. */
export type Empty = Record<never, never>;

/** What one call sends: params (required when the route has required ones) and the JSON body the route takes. */
export type Init<P extends keyof paths, M extends Method> = (Empty extends Params<P, M>
  ? { params?: Params<P, M> }
  : { params: Params<P, M> }) &
  ([Body<P, M>] extends [never] ? { body?: never } : { body: Body<P, M> });

/** `Init` as a trailing argument: optional when nothing in it is required. */
export type InitArg<P extends keyof paths, M extends Method> = Empty extends Init<P, M> ? [init?: Init<P, M>] : [init: Init<P, M>];

/** Params with the route's types erased, for the shared plumbing below the typed signatures. */
export type LooseParams = { path?: Record<string, unknown>; query?: Record<string, unknown> };

const querySerializer = createQuerySerializer();

/** The "/api/..." url a route and its params resolve to: the query key, so it is built the way the request is. */
export function apiUrl(route: string, params: LooseParams = {}): string {
  return createFinalURL(route, { baseUrl: "", params, querySerializer, pathSerializer: defaultPathSerializer });
}

export const api = createClient<paths>({
  // openapi-fetch builds a Request, which needs an absolute url outside a browser (the jsdom tests)
  baseUrl: typeof window === "undefined" ? "" : window.location.origin,
  // looked up on each call, so a test's stubbed fetch is the one used
  fetch: (request) => globalThis.fetch(request),
  // the server rejects non-GET requests without this header (blocks cross-site POSTs)
  headers: { "X-Requested-With": "fantasy-app" },
});
