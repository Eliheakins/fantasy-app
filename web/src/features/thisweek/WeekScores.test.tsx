import { screen, within } from "@testing-library/react";
import { row } from "@/lib/scoreboardFixtures";
import { WeekScores } from "./WeekScores";
import { stubRoutes } from "@/test/fakeApi";
import { renderWithProviders } from "@/test/render";

const ok = (data: unknown) => ({ status: "ok", data, error: null, started_at: null });
const leagues = [
  { league_key: "a", name: "Alpha", roster_id: 1 },
  { league_key: "b", name: "Beta", roster_id: 2 },
];
const final = (a: object, b: object, o: object = {}) => row({ win_prob: null, ...a }, { win_prob: null, ...b }, { status: "Final", ...o });
const scoreboardA = ok([
  final({ team_name: "Seals", points: 120 }, { team_name: "tsd", points: 99.3 }, { matchup_id: 2 }),
  final({ team_name: "Lisan", is_me: true, points: 148.5 }, { team_name: "Flowers", points: 160 }),
]);
const routes: Record<string, object> = {
  "/api/leagues": ok(leagues),
  "/api/leagues/a/scoreboard": scoreboardA,
  "/api/leagues/b/scoreboard": ok([
    row(
      { team_name: "Potty", is_me: true, points: 30, projected: 118, win_prob: 0.64 },
      { team_name: "Bears", points: 22, projected: 104, win_prob: 0.36 },
    ),
  ]),
};

beforeEach(() => {
  routes["/api/leagues"] = ok(leagues);
  routes["/api/leagues/a/scoreboard"] = scoreboardA;
  stubRoutes(routes);
});

function renderScores() {
  renderWithProviders(<WeekScores kickoff={null} />, { route: "/" });
}

describe("WeekScores", () => {
  it("shows the playoff label as text on my row and nowhere else", async () => {
    routes["/api/leagues/a/scoreboard"] = ok([
      final(
        { team_name: "Lisan", is_me: true, points: 148.5 },
        { team_name: "Flowers", points: 160 },
        { playoff_label: "Round 1 of the playoffs" },
      ),
      final({ team_name: "Seals", points: 120 }, { team_name: "tsd", points: 99.3 }, { matchup_id: 2 }),
    ]);
    renderScores();
    expect(await screen.findAllByText("Round 1 of the playoffs")).toHaveLength(1);
  });

  it("shows the league's playoff label when my team has no matchup this week", async () => {
    routes["/api/leagues"] = ok([{ ...leagues[0], playoff_label: "Bye this round" }, leagues[1]]);
    routes["/api/leagues/a/scoreboard"] = ok([final({ team_name: "Seals", points: 120 }, { team_name: "tsd", points: 99.3 })]);
    renderScores();
    const alpha = (await screen.findByRole("heading", { name: "Alpha" })).closest("section")!;
    expect(await within(alpha).findByText("Bye this round")).toBeInTheDocument();
  });

  it("does not repeat the league's playoff label when my matchup carries one", async () => {
    routes["/api/leagues"] = ok([{ ...leagues[0], playoff_label: "Round 1 of the playoffs" }, leagues[1]]);
    routes["/api/leagues/a/scoreboard"] = ok([
      final(
        { team_name: "Lisan", is_me: true, points: 148.5 },
        { team_name: "Flowers", points: 160 },
        { playoff_label: "Round 1 of the playoffs" },
      ),
    ]);
    renderScores();
    await screen.findAllByRole("listitem");
    expect(screen.getAllByText("Round 1 of the playoffs")).toHaveLength(1);
  });

  it("shows the server's no-data text for a league without a scoreboard, not a loading line", async () => {
    routes["/api/leagues/a/scoreboard"] = {
      status: "error",
      data: null,
      error: { code: "no_data", message: "No scoreboard yet." },
      started_at: null,
    };
    renderScores();
    const alpha = (await screen.findByRole("heading", { name: "Alpha" })).closest("section")!;
    expect(await within(alpha).findByText("No scoreboard yet.")).toBeInTheDocument();
    expect(within(alpha).queryByText("Loading scores…")).not.toBeInTheDocument();
  });

  it("says so while the server is still working on a league's scoreboard", async () => {
    routes["/api/leagues/a/scoreboard"] = { status: "running", data: null, error: null, started_at: null };
    renderScores();
    const alpha = (await screen.findByRole("heading", { name: "Alpha" })).closest("section")!;
    expect(await within(alpha).findByText(/^Working/)).toBeInTheDocument();
    expect(within(alpha).queryByText("Loading scores…")).not.toBeInTheDocument();
  });

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
