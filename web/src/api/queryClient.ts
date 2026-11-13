import { QueryClient } from "@tanstack/react-query";

/**
 * The app's query client. `/api` GETs (["api", url]) and kept POST results (["post", ...]) retry once; every other
 * query keeps react-query's default unless it sets its own. Tests use a client without these defaults (no retries).
 */
export function createAppQueryClient(): QueryClient {
  const client = new QueryClient();
  client.setQueryDefaults(["api"], { retry: 1 });
  client.setQueryDefaults(["post"], { retry: 1 });
  return client;
}
