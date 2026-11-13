import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { LeagueProvider } from "@/lib/league";
import { TeamProvider } from "@/lib/TeamProvider";

/** No retries, so a failed request shows its error at once. The app's own retry defaults are not set here. */
export const testQueryClient = (): QueryClient => new QueryClient({ defaultOptions: { queries: { retry: false } } });

type Options = {
  /** Wrap in a MemoryRouter at this entry. Leave out when the test brings its own (data) router or needs none. */
  route?: string;
  /** Wrap in LeagueProvider (outside the test's own router, as in main.tsx, when `route` is left out). */
  league?: boolean;
  /** Wrap in TeamProvider (inside LeagueProvider; needs a router). */
  team?: boolean;
  client?: QueryClient;
};

/** Renders `ui` inside the providers the app gives it: a fresh query client, then optionally router, league and team. */
export function renderWithProviders(ui: ReactElement, { route, league = false, team = false, client = testQueryClient() }: Options = {}) {
  let tree: ReactNode = team ? <TeamProvider>{ui}</TeamProvider> : ui;
  if (league) tree = <LeagueProvider>{tree}</LeagueProvider>;
  if (route !== undefined) tree = <MemoryRouter initialEntries={[route]}>{tree}</MemoryRouter>;
  return { ...render(<QueryClientProvider client={client}>{tree}</QueryClientProvider>), client };
}
