import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Home from "@/pages/Home";

const ok = (data: unknown) => ({ status: "ok", data, error: null, started_at: null });
const league = {
  league_key: "colgate", name: "Colgate", team_name: "Mine", wins: 4, losses: 2, ties: 0, record: "4-2",
  points_for: 800, current_week: 7, scoring_labels: "1 PPR",
};
const option = (o: string, w: number) => ({
  option: o, win_prob: w, share_better: 0.8, floor: 90, median: 110, ceiling: 130,
});
const routes: Record<string, unknown> = {
  "/api/leagues": ok([league]),
  "/api/unmatched": ok({ count: 3, names: [] }),
  "/season-odds": ok([{ is_me: true, p_playoffs: 0.71, p_bye: 0.2, p_title: 0.123, exp_wins: 9.44 }]),
  "/roster": ok([{ sleeper_id: "1", full_name: "Josh Allen", position: "QB", team: "BUF", injury_status: "Q", is_starter: true }]),
  "/live-score": ok([{ side: "me", team_name: "Mine", points: 48.6, projected_final: 57 }]),
  "/win-probability": ok({ options: [option("max_points", 0.62), option("win_prob", 0.7)] }),
  "/actions": ok([{ kind: "Win probability", text: "Start A over B (+4.1 points)" }]),
};

function mockFetch(overrides: Record<string, unknown> = {}) {
  const all = { ...routes, ...overrides };
  const calls: { url: string; method: string }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, method: init?.method ?? "GET" });
    if (url === "/api/live/refresh") return Response.json(ok({ player_rows: 1 }));
    const key = Object.keys(all).find((k) => url === k || url.endsWith(k));
    return Response.json(key ? all[key] : ok([]));
  }));
  return calls;
}

function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><Home /></QueryClientProvider>);
}

afterEach(() => vi.unstubAllGlobals());

describe("Home", () => {
  it("shows loading first", () => {
    mockFetch();
    renderHome();
    expect(screen.getByText("Loading…")).toBeInTheDocument();
  });
  it("shows the running state", async () => {
    mockFetch({ "/api/leagues": { status: "running", data: null, error: null, started_at: null } });
    renderHome();
    expect(await screen.findByText(/Working/)).toHaveAttribute("role", "status");
  });
  it("shows the no-data state", async () => {
    mockFetch({ "/api/leagues": { status: "error", data: null, error: { code: "no_data", message: "Run make refresh first." }, started_at: null } });
    renderHome();
    expect(await screen.findByText("Run make refresh first.")).toBeInTheDocument();
  });
  it("renders odds, actions, roster and caveat when ok, and refresh posts", async () => {
    const calls = mockFetch();
    renderHome();
    expect(await screen.findByText("71%")).toBeInTheDocument();
    expect(screen.getByText("12.3%")).toBeInTheDocument();
    expect(screen.getByText("9.4")).toBeInTheDocument();
    expect(screen.getByText("Odds assume current rosters.")).toBeInTheDocument();
    expect(await screen.findByText("62%")).toBeInTheDocument();
    expect(await screen.findByText("+4.1 ▲")).toBeInTheDocument();
    expect(screen.getByText("clear")).toBeInTheDocument();
    expect(screen.getByText("Josh Allen")).toBeInTheDocument();
    expect(screen.getByText("Q")).toBeInTheDocument();
    expect(screen.getByText("Starting")).toBeInTheDocument();
    expect(screen.getByText("3 active players have no nflverse history yet.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Refresh scores" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.url === "/api/live/refresh")).toBe(true));
  });
  it("shows the empty-actions line", async () => {
    mockFetch({ "/actions": ok([]) });
    renderHome();
    expect(await screen.findByText(/Nothing stands out/)).toBeInTheDocument();
  });
});
