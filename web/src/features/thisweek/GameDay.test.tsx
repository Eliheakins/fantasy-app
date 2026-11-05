import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach } from "vitest";
import { neededLine } from "./gameDayText";
import { ThisWeekBoard } from "./ThisWeekBoard";
import { WinChanceLine } from "./WinChanceLine";

const ok = (data: unknown) => ({ status: "ok", data, error: null, started_at: null });
const point = (run_at: string, win_prob: number, my_points: number) => ({
  league_id: "L1", run_at, week: 9, roster_id: 1, win_prob, my_points, opp_points: 20, my_projected: 110, opp_projected: 100, my_left: 3, opp_left: 4,
});
const history = [point("2026-11-08T17:10:00Z", 0.55, 10), point("2026-11-08T17:20:00Z", 0.62, 18)];
const now = {
  league_id: "L1", week: 9, roster_id: 1, my_team: "Mine", opp_team: "Theirs", win_prob: 0.62,
  my_points: 18, opp_points: 20, my_projected: 110, opp_projected: 100, my_left: 3, opp_left: 4, points_needed: 82,
};
const status = (active: boolean) =>
  ok({ freshness: [], missing_layers: [], simulation_behind_inputs: null, data_version: "v", live_refresh: { enabled: true, active, last_ok_at: null, last_error: null, interval_minutes: 10 } });

let live = true;
let gameDay: () => Response = () => Response.json(ok({ week: 9, as_of: "2026-11-08T17:20:00Z", current: now, history }));
let leaguesFail = false;
let urls: string[] = [];
const count = (needle: string) => urls.filter((u) => u.includes(needle)).length;
beforeEach(() => {
  urls = [];
  live = true;
  leaguesFail = false;
  gameDay = () => Response.json(ok({ week: 9, as_of: "2026-11-08T17:20:00Z", current: now, history }));
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    urls.push(url);
    const path = url.split("?")[0] ?? "";
    if (path === "/api/status") return Response.json(status(live));
    if (path === "/api/leagues") return leaguesFail ? Response.json({ status: "error", data: null, error: { code: "server", message: "down" }, started_at: null }) : Response.json(ok([{ league_key: "a", name: "Alpha", roster_id: 1 }]));
    if (path.endsWith("/digest")) return Response.json(ok({ waivers: [], ideas: {} }));
    if (path === "/api/week-calendar") return Response.json(ok({ week: 9, kickoffs: [], waivers: [] }));
    if (path === "/api/leagues/a/game-day") return gameDay();
    return Response.json(ok([]));
  }));
});
afterEach(() => vi.unstubAllGlobals());

function renderBoard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter><ThisWeekBoard /></MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}
const todoPanel = () => screen.getByRole("heading", { name: "To do, both leagues" }).closest("section")!;

describe("game-day block", () => {
  it("shows the numbers and the win-chance history while a game is on, and the to-do panel steps down", async () => {
    renderBoard();
    expect(await screen.findByText("Alpha: Mine vs Theirs")).toBeInTheDocument();
    expect(await screen.findByText("62%", { selector: "span.text-heading" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /62%.*what drives this/ })).toBeInTheDocument();
    expect(screen.getByText(/Mine: 18\.0 so far.*3 players left/)).toBeInTheDocument();
    expect(screen.getByText(/Theirs: 20\.0 so far.*4 players left/)).toBeInTheDocument();
    expect(screen.getByText(/82\.0 points/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Game day/ }).closest("section")!.className).toContain("bg-panel");
    expect(todoPanel().className).not.toContain("bg-panel");
  });

  it("is absent and asks for nothing more when no game is on", async () => {
    live = false;
    renderBoard();
    expect(await screen.findByRole("heading", { name: "To do, both leagues" })).toBeInTheDocument();
    await waitFor(() => expect(count("/api/status")).toBe(1));
    expect(screen.queryByRole("heading", { name: /Game day/ })).not.toBeInTheDocument();
    expect(count("game-day")).toBe(0);
    expect(todoPanel().className).toContain("bg-panel");
  });

  it("goes away and stops asking for game-day numbers when the games end", async () => {
    const client = renderBoard();
    await screen.findByText("Alpha: Mine vs Theirs");
    live = false;
    await client.invalidateQueries({ queryKey: ["api", "/api/status"] });
    await waitFor(() => expect(screen.queryByRole("heading", { name: /Game day/ })).not.toBeInTheDocument());
    const before = count("game-day");
    await client.invalidateQueries({ queryKey: ["api"] });
    expect(count("game-day")).toBe(before);
    expect(todoPanel().className).toContain("bg-panel");
  });

  it("says when a league's numbers did not load", async () => {
    gameDay = () => Response.json({ status: "error", data: null, error: { code: "server", message: "x" }, started_at: null });
    renderBoard();
    expect(await screen.findByText("Alpha: game-day numbers did not load.")).toHaveAttribute("role", "alert");
  });

  it("says there is no matchup in play when the league has no current numbers", async () => {
    gameDay = () => Response.json(ok({ week: null, as_of: null, current: null, history: [] }));
    renderBoard();
    expect(await screen.findByText("Alpha: no matchup in play this week.")).toBeInTheDocument();
  });

  it("says when the leagues did not load", async () => {
    leaguesFail = true;
    renderBoard();
    const block = (await screen.findByRole("heading", { name: /Game day/ })).closest("section")!;
    expect(await within(block).findByText(/leagues did not load/)).toBeInTheDocument();
  });

  it("keeps the last numbers with a note when a refetch fails", async () => {
    const client = renderBoard();
    await screen.findByText("Alpha: Mine vs Theirs");
    gameDay = () => new Response("nope", { status: 500 });
    await client.invalidateQueries({ queryKey: ["api", "/api/leagues/a/game-day"] });
    expect(await screen.findByText(/last refresh failed/)).toBeInTheDocument();
    expect(screen.getByText("Alpha: Mine vs Theirs")).toBeInTheDocument();
  });
});

describe("points needed in words", () => {
  const base = { my_team: "Mine", opp_team: "Theirs", my_points: 100, opp_points: 90, opp_projected: 95, my_left: 2, opp_left: 2, points_needed: -5 };
  it("reports a finished loss, win and tie plainly", () => {
    const done = { my_left: 0, opp_left: 0 };
    expect(neededLine({ ...base, ...done, my_points: 148.5, opp_points: 160, points_needed: 11.5 })).toBe("Final: lost 148.5 to 160.0.");
    expect(neededLine({ ...base, ...done, my_points: 150.4, opp_points: 130, points_needed: -20.4 })).toBe("Final: won by 20.4.");
    expect(neededLine({ ...base, ...done, my_points: 120, opp_points: 120, points_needed: 0 })).toBe("Final: tied at 120.0.");
  });
  it("says so when I am already past their projection, instead of a negative need", () => {
    expect(neededLine(base)).toBe("You are already 5.0 past Theirs' projected final of 95.0.");
  });
  it("says the points cannot come when I have nobody left but they are still playing", () => {
    expect(neededLine({ ...base, my_left: 0, points_needed: 11.5 })).toMatch(/No players left.*11\.5 points that can't come/);
  });
  it("gives the need and the players left otherwise", () => {
    expect(neededLine({ ...base, points_needed: 12 })).toBe("To reach Theirs' projected final you need 12.0 points from 2 players left.");
  });
});

describe("WinChanceLine", () => {
  it("gives the chart a text equivalent with numbers and one row per tick, plus now", () => {
    render(<WinChanceLine history={history} now={{ at: "2026-11-08T17:30:00Z", win_prob: 0.7 }} />);
    expect(screen.getByRole("img", { name: /from 55% to 70%, 3 updates/ })).toBeInTheDocument();
    const rows = screen.getAllByRole("row");
    expect(rows).toHaveLength(4); // header + two ticks + now
    expect(rows[3]).toHaveTextContent("(now)");
    expect(rows[3]).toHaveTextContent("70%");
    expect(rows[1]).toHaveTextContent(/Sun/);
  });

  it("does not add a now point that repeats the last tick", () => {
    render(<WinChanceLine history={history} now={{ at: history[1]!.run_at, win_prob: 0.62 }} />);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("says there is no history yet with fewer than two points", () => {
    render(<WinChanceLine history={history.slice(0, 1)} />);
    expect(screen.getByText(/builds as the day goes on/)).toBeInTheDocument();
  });
});
