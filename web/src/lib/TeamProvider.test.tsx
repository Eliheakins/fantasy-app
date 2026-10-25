import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { TeamBanner } from "@/components/layout/TeamBanner";
import { useApi } from "@/hooks/useApi";
import { LeagueProvider } from "@/lib/league";
import { TeamProvider } from "@/lib/TeamProvider";
import { useTeam } from "@/lib/teamContext";

const ok = (data: unknown) => ({ status: "ok", data, error: null, started_at: null });
const team = (roster_id: number, team_name: string, is_me: boolean) => ({
  roster_id, team_name, is_me, wins: 1, losses: 0, ties: 0, points_for: 10, record: "1-0",
});
const routes: Record<string, unknown> = {
  "/api/leagues": ok([{ league_key: "a", name: "A" }]),
  "/api/leagues/a/teams": ok([team(1, "Mine", true), team(2, "Rival", false)]),
  "/api/leagues/a/roster": ok([]),
};

function mockFetch(): string[] {
  const urls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    urls.push(url);
    return Response.json(routes[url.split("?")[0] ?? url] ?? ok([]));
  }));
  return urls;
}

function Probe() {
  useApi("/api/leagues/a/roster");
  const { setTeam } = useTeam();
  const { search } = useLocation();
  return (
    <>
      <p data-testid="search">{search}</p>
      <button type="button" onClick={() => setTeam(2)}>pick</button>
      <button type="button" onClick={() => setTeam(null)}>reset</button>
    </>
  );
}

function renderAt(entry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <LeagueProvider>
          <TeamProvider>
            <TeamBanner />
            <Probe />
          </TeamProvider>
        </LeagueProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("TeamProvider", () => {
  it("sends no team and shows no banner by default", async () => {
    const urls = mockFetch();
    renderAt("/");
    await waitFor(() => expect(urls).toContain("/api/leagues/a/roster"));
    expect(urls.some((u) => u.includes("team="))).toBe(false);
    expect(screen.queryByText(/Viewing as/)).not.toBeInTheDocument();
  });

  it("reads ?team= from the URL, sends it, and shows the banner", async () => {
    const urls = mockFetch();
    renderAt("/?team=2&league=a");
    await screen.findByText("Viewing as Rival");
    await waitFor(() => expect(urls).toContain("/api/leagues/a/roster?team=2"));
    expect(urls).not.toContain("/api/leagues/a/teams?team=2");
  });

  it("treats my own roster id as the default", async () => {
    const urls = mockFetch();
    renderAt("/?team=1&league=a");
    await waitFor(() => expect(urls).toContain("/api/leagues/a/roster"));
    expect(screen.queryByText(/Viewing as/)).not.toBeInTheDocument();
  });

  it("ignores a team that is not in the league", async () => {
    const urls = mockFetch();
    renderAt("/?team=99&league=a");
    await waitFor(() => expect(urls).toContain("/api/leagues/a/teams"));
    await waitFor(() => expect(urls).toContain("/api/leagues/a/roster"));
    expect(screen.queryByText(/Viewing as/)).not.toBeInTheDocument();
  });

  it("writes the choice to the URL and clears it again", async () => {
    mockFetch();
    renderAt("/");
    await screen.findByText("pick");
    await userEvent.click(screen.getByText("pick"));
    expect(screen.getByTestId("search")).toHaveTextContent("?team=2&league=a");
    await userEvent.click(screen.getByText("reset"));
    expect(screen.getByTestId("search")).toHaveTextContent("");
  });

  it("back to my team clears the banner", async () => {
    mockFetch();
    renderAt("/?team=2&league=a");
    await userEvent.click(await screen.findByText("Back to my team"));
    await waitFor(() => expect(screen.queryByText(/Viewing as/)).not.toBeInTheDocument());
  });
});
