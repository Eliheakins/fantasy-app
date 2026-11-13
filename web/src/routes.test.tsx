import { screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, matchRoutes, RouterProvider } from "react-router-dom";
import { EXTRA_TITLES, NAV_ITEMS, PUBLIC_TITLES } from "./nav";
import { routes } from "./routes";
import { errorReply, okReply, stubApi } from "@/test/fakeApi";
import { renderWithProviders } from "@/test/render";

vi.mock("@/pages/Ask", async () => ({ default: (await import("@/test/stubPage")).stubPage("Ask") }));
// stands in for a page whose chunk 404s after a redeploy
vi.mock("@/pages/DevViz", () => ({
  default: () => {
    throw new Error("Failed to fetch dynamically imported module");
  },
}));
vi.mock("@/pages/Explore", async () => ({ default: (await import("@/test/stubPage")).stubPage("Explore") }));
vi.mock("@/pages/Lineup", async () => ({ default: (await import("@/test/stubPage")).stubPage("Lineup") }));
vi.mock("@/pages/Moves", async () => ({ default: (await import("@/test/stubPage")).stubPage("Moves") }));
vi.mock("@/pages/Player", async () => ({ default: (await import("@/test/stubPage")).stubPage("Player") }));
vi.mock("@/pages/PlayersCompare", async () => ({ default: (await import("@/test/stubPage")).stubPage("Compare") }));
vi.mock("@/pages/Players", async () => ({ default: (await import("@/test/stubPage")).stubPage("Players") }));
vi.mock("@/pages/Scorecard", async () => ({ default: (await import("@/test/stubPage")).stubPage("Model") }));
vi.mock("@/pages/Season", async () => ({ default: (await import("@/test/stubPage")).stubPage("Season") }));
vi.mock("@/pages/ThisWeek", async () => ({ default: (await import("@/test/stubPage")).stubPage("ThisWeek") }));

beforeEach(() => {
  const status = {
    freshness: [],
    missing_layers: [],
    simulation_behind_inputs: null,
    refresh_runs: [],
    live_refresh: { enabled: false, active: false, last_ok_at: null },
  };
  stubApi(({ url }) =>
    url.startsWith("/api/me/")
      ? // no account (login off), so the first-visit dialog stays shut and the nav can be clicked
        errorReply("unauthorized", "Sign in", 401)
      : url === "/api/status"
        ? okReply(status)
        : url === "/api/leagues"
          ? okReply([])
          : url === "/api/auth/me"
            ? okReply({ email: "me@example.com", is_admin: false, sleeper_user_id: null })
            : url === "/api/stat/health"
              ? errorReply("no_data", "No stat data", 404) // the banner then reads no stat health
              : undefined,
  );
  window.localStorage.clear();
});

function open(entry: string) {
  const router = createMemoryRouter(routes, { initialEntries: [entry] });
  renderWithProviders(<RouterProvider router={router} />, { league: true });
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

  it("mounts /players/compare and /players/find ahead of /players/:gsisId", async () => {
    for (const [path, name] of [
      ["/players/compare?p=a&p=b", "Compare"],
      ["/players/find", "Explore"],
    ] as const) {
      const router = createMemoryRouter(routes, { initialEntries: [path] });
      const view = renderWithProviders(<RouterProvider router={router} />, { league: true });
      expect(await screen.findByTestId("page")).toHaveTextContent(`${name} ${path}`);
      expect(screen.getAllByRole("link", { name: "Players" }).some((l) => l.getAttribute("aria-current") === "page")).toBe(true);
      view.unmount();
    }
  });

  it("mounts /players/:gsisId on the player page and keeps the Players tab active there and on /players/find", async () => {
    for (const [path, name] of [
      ["/players/00-0012345?league=a", "Player"],
      ["/players/find", "Explore"],
    ] as const) {
      const router = createMemoryRouter(routes, { initialEntries: [path] });
      const view = renderWithProviders(<RouterProvider router={router} />, { league: true });
      expect(await screen.findByTestId("page")).toHaveTextContent(`${name} ${path.split("?")[0]}`);
      expect(screen.getAllByRole("link", { name: "Players" }).some((l) => l.getAttribute("aria-current") === "page")).toBe(true);
      view.unmount();
    }
  });

  it("mounts each tab and the non-tab routes", async () => {
    for (const [path, name] of [
      ["/", "ThisWeek"],
      ["/lineup", "Lineup"],
      ["/moves", "Moves"],
      ["/season", "Season"],
      ["/players", "Players"],
      ["/ask", "Ask"],
      ["/model", "Model"],
    ] as const) {
      const router = createMemoryRouter(routes, { initialEntries: [path] });
      const view = renderWithProviders(<RouterProvider router={router} />, { league: true });
      expect(await screen.findByTestId("page")).toHaveTextContent(`${name} ${path}`);
      view.unmount();
    }
  });

  it("mounts a route at every nav tab and every other titled path in nav.ts", () => {
    const paths = [...NAV_ITEMS.map((n) => n.path), ...Object.keys(EXTRA_TITLES), ...Object.keys(PUBLIC_TITLES)];
    for (const path of paths) expect(matchRoutes(routes, path)?.at(-1)?.route.path, path).toBe(path);
  });

  it("titles the sign-in page from nav.ts", async () => {
    open("/login");
    await waitFor(() => expect(document.title).toBe("Sign in · Fantasy"));
  });

  it("a page that fails to load shows the error boundary with a Reload button", async () => {
    open("/dev/viz");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("This page could not load");
    expect(within(alert).getByRole("button", { name: "Reload" })).toBeInTheDocument();
  });

  it("an unknown path shows the not-found page", async () => {
    open("/nope");
    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
  });
});
