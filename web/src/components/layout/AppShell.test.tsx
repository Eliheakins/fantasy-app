import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "./AppShell";
import { PageHeader } from "@/components/PageHeader";
import { rememberExplore } from "@/features/explore/routeMemory";
import { LeagueProvider } from "@/lib/league";
import { MORE_ITEMS, NAV_GROUPS, NAV_ITEMS, TAB_ITEMS } from "@/nav";

const EXPLORE_QUERY = "p=00-0033873&s=rec_yards&f=season-2026&g=total&m=50&o=rec_yards&n=10&by=week&who=teams&t=KC&side=defense";

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

function renderAt(entry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <LeagueProvider>
          <Routes>
            <Route element={<AppShell />}>
              <Route path="*" element={<PageHeader title="page" />} />
            </Route>
          </Routes>
        </LeagueProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const rail = () => within(screen.getByRole("navigation", { name: "Main" }));
const tabs = () => within(screen.getByRole("navigation", { name: "Main tabs" }));
const search = (link: HTMLElement) => new URL(link.getAttribute("href") ?? "", "http://x").searchParams;

describe("nav links", () => {
  it("carry only league and team from an Explore URL", () => {
    rememberExplore("");
    renderAt(`/explore?league=a&team=2&${EXPLORE_QUERY}`);

    const links = [...rail().getAllByRole("link"), ...tabs().getAllByRole("link")].filter((l) => l.textContent?.trim() !== "Explore");
    expect(links.length).toBeGreaterThan(NAV_ITEMS.length);
    for (const link of links) {
      expect([...search(link).keys()].sort()).toEqual(["league", "team"]);
      expect(search(link).get("team")).toBe("2");
    }
  });

  it("send the Explore link to the current query while on Explore", () => {
    rememberExplore("?s=rec_yards");
    renderAt("/explore?league=a&team=2&s=rush_yards&t=KC");

    const query = search(rail().getByRole("link", { name: "Explore" }));

    expect(query.getAll("s")).toEqual(["rush_yards"]);
    expect(query.get("t")).toBe("KC");
    expect(query.get("team")).toBe("2");
  });

  it("send the Explore link to the last Explore query, with the current league and team", () => {
    rememberExplore(`?league=old&team=9&${EXPLORE_QUERY}`);
    renderAt("/lineup?league=a&team=2");

    const query = search(rail().getByRole("link", { name: "Explore" }));

    expect(query.get("league")).toBe("a");
    expect(query.get("team")).toBe("2");
    expect(query.get("s")).toBe("rec_yards");
    expect(query.get("t")).toBe("KC");
    expect(query.get("p")).toBe("00-0033873");
  });
});

describe("rail", () => {
  it("shows the three group labels and every entry under its group", () => {
    renderAt("/");

    for (const group of NAV_GROUPS) {
      const list = rail().getByRole("list", { name: group });
      const expected = NAV_ITEMS.filter((i) => i.group === group).map((i) => i.label);
      expect(within(list).getAllByRole("link").map((l) => l.textContent?.trim())).toEqual(expected);
    }
    expect(NAV_GROUPS).toEqual(["Decide", "Season", "Research"]);
  });
});

describe("phone tab bar", () => {
  it("has the four tabs and More", () => {
    renderAt("/");
    expect(tabs().getAllByRole("link").map((l) => l.textContent?.trim())).toEqual(["Home", "Lineup", "Waivers", "Trades"]);
    expect(tabs().getByRole("button", { name: "More" })).toBeInTheDocument();
  });

  it("opens a More sheet with exactly the entries that have no tab, and closes on Esc", async () => {
    renderAt("/lineup?league=a&team=2");
    await userEvent.click(tabs().getByRole("button", { name: "More" }));

    const sheet = screen.getByRole("dialog", { name: "More" });
    const links = within(sheet).getAllByRole("link");
    expect(links.map((l) => l.textContent?.trim())).toEqual(MORE_ITEMS.map((i) => i.label));
    expect(TAB_ITEMS.length + MORE_ITEMS.length).toBe(NAV_ITEMS.length);
    expect(links.every((l) => search(l).get("team") === "2")).toBe(true);

    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("closes the sheet after choosing a page and leaves focus on the new page's heading", async () => {
    renderAt("/");
    await userEvent.click(tabs().getByRole("button", { name: "More" }));
    await userEvent.click(within(screen.getByRole("dialog")).getByRole("link", { name: "Explore" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "page" }));
  });

  it("closes the sheet when the location changes another way", async () => {
    renderAt("/");
    await userEvent.click(tabs().getByRole("button", { name: "More" }));
    // Back/forward and links outside the sheet change the location while it is open (the page behind is aria-hidden).
    fireEvent.click(document.querySelector<HTMLElement>('nav[aria-label="Main"] a[href^="/lineup"]')!);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("wraps the sheet links in a labelled nav", async () => {
    renderAt("/");
    await userEvent.click(tabs().getByRole("button", { name: "More" }));
    expect(within(screen.getByRole("dialog")).getByRole("navigation", { name: "More pages" })).toBeInTheDocument();
  });
});
