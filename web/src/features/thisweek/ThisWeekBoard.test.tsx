import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach } from "vitest";
import { Answer } from "./Answer";
import { ThisWeekBoard } from "./ThisWeekBoard";

const ok = (data: unknown) => ({ status: "ok", data, error: null, started_at: null });
const leagues = [
  { league_key: "a", name: "Alpha", roster_id: 1 },
  { league_key: "b", name: "Beta", roster_id: 2 },
];
const idea = { kind: "waiver", get: "Coleman", give: "Bernard", rank: 1, playoff_delta: 0.023, delta_points: 3.1 };
const digest = (waivers: unknown[]) => ok({ waivers, ideas: {} });
const calendar = {
  week: 9,
  kickoffs: [
    { team: "A", kickoff: "2026-11-08T13:00:00-05:00" },
    { team: "B", kickoff: "2026-11-08T13:00:00-05:00" },
  ],
  waivers: [
    { league_key: "a", name: "Alpha", day_of_week: 2, daily: false },
    { league_key: "b", name: "Beta", day_of_week: 2, daily: false },
  ],
};
const routes: [string, unknown][] = [
  ["/api/leagues/a/actions", ok([])],
  ["/api/leagues/b/actions", ok([{ kind: "Lineup", text: "Start A over B (+4.1 points)", delta_points: 4.1 }])],
  ["/api/leagues/a/digest", digest([idea])],
  ["/api/leagues/b/digest", digest([])],
  [
    "/api/leagues/a/odds-history",
    ok([
      { run_at: "2026-10-30T10:00:00", roster_id: 1, p_playoffs: 0.5, p_title: 0.1 },
      { run_at: "2026-11-03T10:00:00", roster_id: 1, p_playoffs: 0.58, p_title: 0.1 },
    ]),
  ],
  ["/api/leagues/b/odds-history", ok([])],
  ["/api/leagues/a/status-changes", ok([{ sleeper_id: "s1", full_name: "James Cook III", before: null, after: "Out" }])],
  ["/api/leagues/b/status-changes", ok([])],
  ["/api/week-calendar", ok(calendar)],
  ["/api/leagues", ok(leagues)],
];

let urls: string[] = [];
beforeEach(() => {
  urls = [];
  window.localStorage.clear();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-04T15:00:00Z")); // Wednesday morning in New York
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      urls.push(url);
      const hit = routes.find(([prefix]) => url.split("?")[0] === prefix);
      return Response.json(hit ? hit[1] : ok([]));
    }),
  );
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function renderBoard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <p data-testid="answer">
          <Answer />
        </p>
        <ThisWeekBoard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const visitAt = (key: string) => JSON.parse(window.localStorage.getItem(`fantasy.lastVisit.${key}`) ?? "null");

describe("to-dos for both leagues", () => {
  it("lists them in one list, each tagged with its league, the waiver due today first, and says so in the answer", async () => {
    renderBoard();
    const items = await waitFor(() => {
      const rows = within(screen.getByRole("heading", { name: "To do, both leagues" }).closest("section")!).getAllByRole("listitem");
      expect(rows).toHaveLength(2);
      return rows;
    });
    expect(items[0]).toHaveTextContent("Add Coleman, drop Bernard");
    expect(items[0]).toHaveTextContent("Alpha");
    expect(items[0]).toHaveTextContent("by Wed 4");
    expect(items[1]).toHaveTextContent("Start A over B");
    expect(items[1]).toHaveTextContent("Beta");
    expect(within(items[0]!).getByRole("button", { name: /\+2\.3.*what drives this/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Add Coleman, drop Bernard" })).toHaveAttribute("href", "/moves?league=a");
    expect(screen.getByRole("link", { name: "Start A over B" })).toHaveAttribute("href", "/lineup?league=b");
    expect(screen.getByTestId("answer")).toHaveTextContent("First: Add Coleman, drop Bernard (Alpha, by Wed 4)");
  });

  it("marks now on the week strip", async () => {
    renderBoard();
    const today = await screen.findByText("Now");
    expect(today.closest("li")).toHaveAttribute("aria-current", "date");
    expect(today.closest("li")).toHaveTextContent("Wed 4");
  });
});

describe("Since you last looked", () => {
  it("says it is the first visit, then stores the time after showing", async () => {
    renderBoard();
    expect((await screen.findAllByText("First visit: we'll show changes from next time.")).length).toBe(2);
    await waitFor(() => expect(visitAt("a")).toMatchObject({ adds: ["Coleman"] }));
    expect(visitAt("b")).toMatchObject({ adds: [] });
    expect(urls.some((u) => u.includes("status-changes"))).toBe(false); // nothing to compare with yet
  });

  it("shows odds change, status change and a new add since the stored visit, before overwriting it", async () => {
    window.localStorage.setItem("fantasy.lastVisit.a", JSON.stringify({ at: "2026-11-01T10:00:00.000Z", adds: ["Old"] }));
    renderBoard();
    expect(await screen.findByText(/James Cook III: healthy to Out/)).toBeInTheDocument();
    expect(screen.getByText(/New on your waiver list: Coleman/)).toBeInTheDocument();
    expect(screen.getByText(/Season odds:/)).toHaveTextContent("+8.0");
    expect(screen.getByRole("button", { name: /\+8\.0.*what drives this/ })).toBeInTheDocument();
    expect(urls.some((u) => u.includes("status-changes?since=2026-11-01T10%3A00%3A00.000Z"))).toBe(true);
    await waitFor(() => expect(visitAt("a").at).toBe("2026-11-04T15:00:00.000Z"));
  });

  it("works when storage throws", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    renderBoard();
    expect((await screen.findAllByText("First visit: we'll show changes from next time.")).length).toBe(2);
    expect(await screen.findByText("Add Coleman, drop Bernard")).toBeInTheDocument();
  });

  it("keeps the stored visit when the page is reloaded within half an hour", async () => {
    const recent = { at: "2026-11-04T14:50:00.000Z", adds: ["Old"] };
    window.localStorage.setItem("fantasy.lastVisit.a", JSON.stringify(recent));
    renderBoard();
    expect(await screen.findByText(/New on your waiver list: Coleman/)).toBeInTheDocument();
    await waitFor(() => expect(visitAt("b")).not.toBeNull()); // b was a first visit and is stored
    expect(visitAt("a")).toEqual(recent);
  });

  it("compares the whole add list, not only the part that is stored", async () => {
    const many = Array.from({ length: 8 }, (_, i) => ({ ...idea, get: `Add${i}` }));
    const stored = many.map((m) => m.get);
    routes.unshift(["/api/leagues/a/digest", digest(many)]);
    window.localStorage.setItem("fantasy.lastVisit.a", JSON.stringify({ at: "2026-11-01T10:00:00.000Z", adds: stored }));
    renderBoard();
    expect(await screen.findByText(/James Cook III/)).toBeInTheDocument();
    expect(screen.queryByText(/New on your waiver list/)).not.toBeInTheDocument();
    await waitFor(() => expect(visitAt("a").adds).toHaveLength(8));
    routes.shift();
  });
});

describe("failures and a stale calendar", () => {
  it("says the leagues did not load instead of 'nothing to do'", async () => {
    routes.unshift(["/api/leagues", { status: "error", data: null, error: { code: "server", message: "boom" }, started_at: null }]);
    renderBoard();
    expect(await screen.findAllByText(/The leagues did not load/)).not.toHaveLength(0);
    expect(screen.queryByText(/Nothing needs doing/)).not.toBeInTheDocument();
    routes.shift();
  });

  it("tells you when every kickoff of the data's week is outside the strip", async () => {
    routes.unshift([
      "/api/week-calendar",
      ok({
        ...calendar,
        week: 8,
        kickoffs: [
          { team: "A", kickoff: "2026-11-01T13:00:00-05:00" },
          { team: "B", kickoff: null },
        ],
      }),
    ]);
    renderBoard();
    expect(await screen.findByText(/All kickoffs for week 8 are outside/)).toBeInTheDocument();
    expect(screen.getByText(/1 teams have no kickoff time/)).toBeInTheDocument();
    routes.shift();
  });
});
