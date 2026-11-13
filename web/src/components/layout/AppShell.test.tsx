import { screen, within } from "@testing-library/react";
import { Route, Routes } from "react-router";
import { AppShell } from "./AppShell";
import { PageHeader } from "@/components/PageHeader";
import { rememberExplore } from "@/stat/react/routeMemory";
import { NAV_ITEMS } from "@/nav";
import { errorReply, okReply, type Reply, stubApi } from "@/test/fakeApi";
import { renderWithProviders } from "@/test/render";

const FIVE = ["This week", "Lineup", "Moves", "Season", "Players"];

beforeEach(() => {
  const status = {
    freshness: [],
    missing_layers: [],
    simulation_behind_inputs: null,
    refresh_runs: [],
    live_refresh: { enabled: false, active: false, last_ok_at: null },
  };
  const shell: Record<string, Reply> = {
    "/api/status": okReply(status),
    "/api/leagues": okReply([]),
    "/api/auth/me": okReply({ email: "me@example.com", is_admin: false, sleeper_user_id: null }),
    "/api/stat/health": errorReply("no_data", "No stat data", 404), // the banner then reads no stat health
  };
  stubApi(({ url }) => shell[url]);
  window.localStorage.clear();
  rememberExplore("");
});

function renderAt(entry: string) {
  renderWithProviders(
    <Routes>
      <Route element={<AppShell />}>
        <Route path="*" element={<PageHeader title="page" />} />
      </Route>
    </Routes>,
    { route: entry, league: true },
  );
}

const desktop = () => within(screen.getByRole("navigation", { name: "Main" }));
const tabs = () => within(screen.getByRole("navigation", { name: "Main tabs" }));
const search = (link: HTMLElement) => new URL(link.getAttribute("href") ?? "", "http://x").searchParams;

describe("tabs", () => {
  it("are the five pages in order, on the top row and the phone bottom bar", () => {
    renderAt("/");

    expect(NAV_ITEMS.map((i) => i.label)).toEqual(FIVE);
    expect(
      desktop()
        .getAllByRole("link")
        .map((l) => l.textContent?.trim()),
    ).toEqual(FIVE);
    expect(
      tabs()
        .getAllByRole("link")
        .map((l) => l.textContent?.trim()),
    ).toEqual(FIVE);
  });

  it("have no More button or sheet", () => {
    renderAt("/");

    expect(screen.queryByRole("button", { name: "More" })).toBeNull();
  });

  it("mark the current page", () => {
    renderAt("/moves?view=trades");

    expect(desktop().getByRole("link", { name: "Moves" })).toHaveAttribute("aria-current", "page");
    expect(tabs().getByRole("link", { name: "Moves" })).toHaveAttribute("aria-current", "page");
    expect(desktop().getByRole("link", { name: "This week" })).not.toHaveAttribute("aria-current");
  });
});

describe("nav links", () => {
  it("carry only league, team and week from a page with other params", () => {
    renderAt("/moves?league=a&team=2&week=6&view=trades&p=x&q=y");

    const links = [...desktop().getAllByRole("link"), ...tabs().getAllByRole("link")];
    expect(links).toHaveLength(10);
    for (const link of links) {
      expect([...search(link).keys()].sort()).toEqual(["league", "team", "week"]);
      expect(search(link).get("week")).toBe("6");
      expect(search(link).get("team")).toBe("2");
    }
  });

  it("carry nothing when the URL has no shared params", () => {
    renderAt("/season");

    expect(desktop().getByRole("link", { name: "Lineup" })).toHaveAttribute("href", "/lineup");
  });

  it("keep league, team and week from an Explore URL on /players/find", () => {
    renderAt("/players/find?league=a&team=2&week=3&p=00-0033873&s=rec_yards");

    expect(desktop().getByRole("link", { name: "Players" })).toHaveAttribute("href", "/players?league=a&team=2&week=3");
  });
});

describe("footer", () => {
  it("links to the model scorecard keeping league, team and week", () => {
    renderAt("/lineup?league=a&team=2&week=6&view=x");

    const link = screen.getByRole("link", { name: "Model scorecard" });
    expect(new URL(link.getAttribute("href") ?? "", "http://x").pathname).toBe("/model");
    expect([...search(link).keys()].sort()).toEqual(["league", "team", "week"]);
    expect(screen.getByText(/Data from Sleeper and nflverse/)).toBeInTheDocument();
  });
});
