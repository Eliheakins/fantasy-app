import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { LeagueProvider } from "@/lib/league";
import { routes } from "./routes";

vi.mock("@/pages/Ask", async () => ({ default: (await import("@/test/stubPage")).stubPage("Ask") }));
vi.mock("@/pages/DevViz", async () => ({ default: (await import("@/test/stubPage")).stubPage("DevViz") }));
vi.mock("@/pages/Explore", async () => ({ default: (await import("@/test/stubPage")).stubPage("Explore") }));
vi.mock("@/pages/Lineup", async () => ({ default: (await import("@/test/stubPage")).stubPage("Lineup") }));
vi.mock("@/pages/Moves", async () => ({ default: (await import("@/test/stubPage")).stubPage("Moves") }));
vi.mock("@/pages/Players", async () => ({ default: (await import("@/test/stubPage")).stubPage("Players") }));
vi.mock("@/pages/Scorecard", async () => ({ default: (await import("@/test/stubPage")).stubPage("Model") }));
vi.mock("@/pages/Season", async () => ({ default: (await import("@/test/stubPage")).stubPage("Season") }));
vi.mock("@/pages/ThisWeek", async () => ({ default: (await import("@/test/stubPage")).stubPage("ThisWeek") }));

beforeEach(() => {
  const status = { freshness: [], missing_layers: [], simulation_behind_inputs: null, live_refresh: { enabled: false, active: false, last_ok_at: null } };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) =>
      Response.json({ status: "ok", data: url.startsWith("/api/status") ? status : [], error: null, started_at: null }),
    ),
  );
  window.localStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

function open(entry: string) {
  const router = createMemoryRouter(routes, { initialEntries: [entry] });
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <LeagueProvider>
        <RouterProvider router={router} />
      </LeagueProvider>
    </QueryClientProvider>,
  );
  return router;
}

const Q = "league=a&team=2&week=5";

describe("route config", () => {
  it.each([
    ["/waivers", "/moves", "view=fa"],
    ["/trades", "/moves", "view=trades"],
    ["/outlook", "/season", ""],
    ["/scoreboard", "/season", ""],
    ["/league", "/season", ""],
    ["/digest", "/", ""],
    ["/scorecard", "/model", ""],
    ["/explore", "/players/find", "s=rec_yards"],
  ])("%s redirects to %s keeping the query", async (from, to, extra) => {
    const router = open(`${from}?${Q}&${extra}`);
    await waitFor(() => expect(router.state.location.pathname).toBe(to));
    const params = new URLSearchParams(router.state.location.search);
    for (const pair of `${Q}&${extra}`.split("&").filter(Boolean)) {
      const [k, v] = pair.split("=");
      expect(params.get(k ?? "")).toBe(v);
    }
    expect(await screen.findByTestId("page")).toHaveTextContent(to === "/" ? "ThisWeek" : /\S/);
  });

  it("mounts /players/find on Explore, not Players", async () => {
    open("/players/find?s=rec_yards");
    expect(await screen.findByTestId("page")).toHaveTextContent("Explore /players/find?s=rec_yards");
  });

  it("mounts each tab and the non-tab routes", async () => {
    for (const [path, name] of [["/", "ThisWeek"], ["/lineup", "Lineup"], ["/moves", "Moves"], ["/season", "Season"], ["/players", "Players"], ["/ask", "Ask"], ["/model", "Model"]] as const) {
      const router = createMemoryRouter(routes, { initialEntries: [path] });
      const view = render(
        <QueryClientProvider client={new QueryClient()}>
          <LeagueProvider>
            <RouterProvider router={router} />
          </LeagueProvider>
        </QueryClientProvider>,
      );
      expect(await screen.findByTestId("page")).toHaveTextContent(`${name} ${path}`);
      view.unmount();
    }
  });

  it("an unknown path shows the not-found page", async () => {
    open("/nope");
    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
  });
});
