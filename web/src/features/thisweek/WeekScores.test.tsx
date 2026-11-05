import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { row } from "@/lib/scoreboardFixtures";
import { WeekScores } from "./WeekScores";

const ok = (data: unknown) => ({ status: "ok", data, error: null, started_at: null });
const leagues = [{ league_key: "a", name: "Alpha", roster_id: 1 }, { league_key: "b", name: "Beta", roster_id: 2 }];
const final = (a: object, b: object, o: object = {}) => row({ win_prob: null, ...a }, { win_prob: null, ...b }, { status: "Final", ...o });
const routes: Record<string, unknown> = {
  "/api/leagues": ok(leagues),
  "/api/leagues/a/scoreboard": ok([
    final({ team_name: "Seals", points: 120 }, { team_name: "tsd", points: 99.3 }, { matchup_id: 2 }),
    final({ team_name: "Lisan", is_me: true, points: 148.5 }, { team_name: "Flowers", points: 160 }),
  ]),
  "/api/leagues/b/scoreboard": ok([row({ team_name: "Potty", is_me: true, points: 30, projected: 118, win_prob: 0.64 }, { team_name: "Bears", points: 22, projected: 104, win_prob: 0.36 })]),
};

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => Response.json(routes[url.split("?")[0] ?? ""] ?? ok([]))));
});
afterEach(() => vi.unstubAllGlobals());

function renderScores() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter><WeekScores kickoff={null} /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("WeekScores", () => {
  it("groups every matchup by league with my matchup first", async () => {
    renderScores();
    const alpha = (await screen.findByRole("heading", { name: "Alpha" })).closest("section")!;
    const games = await within(alpha).findAllByRole("listitem");
    expect(games).toHaveLength(2);
    expect(games[0]).toHaveAccessibleName("Lisan (you) 148.5, Flowers 160.0, Final");
    expect(games[0]!.className).toContain("mine-row");
    expect(games[1]).toHaveAccessibleName("Seals 120.0, tsd 99.3, Final");
    expect(await screen.findByRole("heading", { name: "Beta" })).toBeInTheDocument();
  });

  it("a live matchup shows points so far, the projection and the win chance", async () => {
    renderScores();
    const beta = (await screen.findByRole("heading", { name: "Beta" })).closest("section")!;
    const game = await within(beta).findByRole("listitem");
    expect(game).toHaveTextContent("Live");
    expect(game).toHaveTextContent("30.0");
    expect(game).toHaveTextContent("64%");
    expect(game).toHaveTextContent("proj 118.0");
  });
});
