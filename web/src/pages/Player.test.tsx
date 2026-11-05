import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import userEvent from "@testing-library/user-event";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ApiState } from "@/api/envelope";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { TeamContext } from "@/lib/teamContext";
import { runStatQuery } from "@/stat/engine/statQuery";
import { fetchManifest } from "@/stat/lib/api";
import { getPlayersByIds } from "@/stat/lib/players";
import Player from "./Player";

vi.mock("@/api/useEnvelope", () => ({ useEnvelopeQuery: vi.fn() }));
vi.mock("@/stat/engine/statQuery", () => ({ runStatQuery: vi.fn() }));
vi.mock("@/stat/lib/api", () => ({ fetchManifest: vi.fn() }));
vi.mock("@/stat/lib/players", () => ({ getPlayersByIds: vi.fn() }));

const manifest = {
  schema_version: 1, built_at: "t", nflreadpy_version: "0", player_index: null, player_game: null, players: null,
  seasons: [{ season: 2026, path: "s.parquet", rows: 1, max_week: 9, has_participation: true }],
};
const gameLog = {
  columns: ["player_id", "season", "week", "m_rec_receptions", "m_rec_yards"],
  rows: [
    { player_id: "00-1", season: 2026, week: 1, m_rec_receptions: 7, m_rec_yards: 101 },
    { player_id: "00-1", season: 2026, week: 2, m_rec_receptions: 5, m_rec_yards: 64 },
  ],
};
const ready = <T,>(data: T): ApiState<T> => ({ kind: "ready", data }) as ApiState<T>;
const failed = { kind: "error", error: { message: "boom", code: null }, retry: () => {} } as ApiState<never>;

const profile = {
  gsis_id: "00-1", full_name: "Ja'Marr Chase", position: "WR", week: 5, result_week: null, result_points: null, is_out: false, projection: 18, p10: 6, median: 17.5, p90: 31, chance_to_play: 1,
  injury: null, injury_note: null, ros_points: 90, replacement_name: "Free Guy", replacement_points: 60, ros_over_replacement: 30,
  outlook_label: null, why: null, role_weeks: [],
};

function mockApi(points: ApiState<unknown>, owners: ApiState<unknown> = ready({ rows: [{ gsis_id: "00-1", owner: "Lisan Al-Caleb", is_mine: true }], unmatched: 0 })) {
  vi.mocked(useEnvelopeQuery).mockImplementation(((path: string | null) =>
    path?.includes("/player-points") ? points : path?.includes("/owners") ? owners : path?.includes("/profile") ? ready(profile) : path?.includes("/market-values") ? ready([]) : { kind: "loading" }) as typeof useEnvelopeQuery);
}

function renderPage(entry = "/players/00-1?league=a&team=2&week=5") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TeamContext.Provider value={{ team: 2, league: "a", teams: [], viewed: null, setTeam: () => {}, notice: null, dismissNotice: () => {} }}>
        <MemoryRouter initialEntries={[entry]}>
          <Routes>
            <Route path="/players/:gsisId" element={<Player />} />
          </Routes>
        </MemoryRouter>
      </TeamContext.Provider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(fetchManifest).mockResolvedValue(manifest as never);
  vi.mocked(runStatQuery).mockResolvedValue(gameLog as never);
  vi.mocked(getPlayersByIds).mockImplementation((async (_m: unknown, ids: string[]) => ids.includes("00-1") ? [{ gsis_id: "00-1", full_name: "Ja'Marr Chase", position: "WR", team: "CIN", headshot_url: null }] : []) as never);
  mockApi(ready([{ week: 1, points: 21.1 }, { week: 2, points: 12.4 }]));
});
afterEach(() => vi.resetAllMocks());

describe("Player page", () => {
  it("shows the name, eyebrow, owner, the game log rows and league points by week", async () => {
    renderPage();
    expect(await screen.findByRole("heading", { level: 1, name: "Ja'Marr Chase" })).toBeInTheDocument();
    expect(screen.getByText("Players · WR · CIN")).toBeInTheDocument();
    expect(await screen.findByText(/Lisan Al-Caleb/)).toBeInTheDocument();
    const rows = await screen.findAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[1]!).getAllByRole("cell").map((c) => c.textContent)).toEqual(["1", "7", "101", "21.1"]);
    expect(within(rows[2]!).getAllByRole("cell").map((c) => c.textContent)).toEqual(["2", "5", "64", "12.4"]);
    expect(vi.mocked(runStatQuery).mock.calls[0]![0]).toMatchObject({
      statIds: ["rec_receptions", "rec_yards"], gsisIds: ["00-1"], split: "week", granularity: "total",
      filterChipState: { "season-2026": true, "stype-reg": true },
    });
  });

  it("answers with the next game range under the h1, in a tinted Next game panel, and links to Compare", async () => {
    renderPage();
    expect(await screen.findByText("Median 17.5 points in week 5, likely between 6.0 and 31.0.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Next game" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Rest of season" })).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /compare with/i });
    const href = new URL(link.getAttribute("href") ?? "", "http://x");
    expect(href.pathname).toBe("/players/compare");
    expect(href.searchParams.getAll("p")).toEqual(["00-1"]);
    expect(href.searchParams.get("league")).toBe("a");
  });

  it("shows a not-found state for an unknown id", async () => {
    renderPage("/players/00-nope");
    expect(await screen.findByRole("heading", { level: 1, name: "Player not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to Players" })).toHaveAttribute("href", "/players");
  });

  it("shows the load error with a retry when the player list fails", async () => {
    vi.mocked(getPlayersByIds).mockRejectedValue(new Error("no players file"));
    renderPage();
    expect(await screen.findByText(/no players file/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Player" })).toBeInTheDocument();
    vi.mocked(getPlayersByIds).mockResolvedValue([{ gsis_id: "00-1", full_name: "Ja'Marr Chase", position: "WR", team: "CIN", headshot_url: null }] as never);
    await userEvent.setup().click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Ja'Marr Chase" })).toBeInTheDocument();
  });

  it("shows a Callout and keeps league points when the engine fails", async () => {
    vi.mocked(runStatQuery).mockRejectedValue(new Error("shard missing"));
    renderPage();
    expect(await screen.findByText(/shard missing/)).toBeInTheDocument();
    expect(screen.getByText("21.1")).toBeInTheDocument();
  });

  it("keeps the game log when the league points fail", async () => {
    mockApi(failed);
    renderPage();
    expect(await screen.findByText("101")).toBeInTheDocument();
    expect(screen.getByText(/league points did not load: boom/i)).toBeInTheDocument();
  });

  it("does not claim there are no games when the game log failed", async () => {
    vi.mocked(runStatQuery).mockRejectedValue(new Error("shard missing"));
    mockApi(ready([]));
    renderPage();
    expect(await screen.findByText(/shard missing/)).toBeInTheDocument();
    expect(screen.queryByText(/no games this season/i)).toBeNull();
  });

  it("Open in Find players keeps league, team and week", async () => {
    renderPage();
    const link = await screen.findByRole("link", { name: /open in find players/i });
    const href = new URL(link.getAttribute("href") ?? "", "http://x");
    expect(href.pathname).toBe("/players/find");
    expect(href.searchParams.get("p")).toBe("00-1");
    expect(href.searchParams.get("league")).toBe("a");
    expect(href.searchParams.get("team")).toBe("2");
    expect(href.searchParams.get("week")).toBe("5");
  });

  it("sets the document title to the player's name once loaded", async () => {
    renderPage();
    expect(document.title).toBe("Player · Fantasy");
    await screen.findByRole("heading", { level: 1, name: "Ja'Marr Chase" });
    expect(document.title).toBe("Ja'Marr Chase · Fantasy");
  });

  it("shows league points to one decimal even below 1", async () => {
    mockApi(ready([{ week: 1, points: 0.2 }, { week: 2, points: 12.4 }]));
    renderPage();
    expect(await screen.findByText("0.2")).toBeInTheDocument();
  });

  it("does not run the engine for a position with no stat lines", async () => {
    vi.mocked(getPlayersByIds).mockResolvedValue([{ gsis_id: "00-1", full_name: "Some Kicker", position: "K", team: "BUF", headshot_url: null }] as never);
    renderPage();
    expect(await screen.findByText("No stat lines for this position.")).toBeInTheDocument();
    expect(runStatQuery).not.toHaveBeenCalled();
  });

  it("keeps projection wording out of the game log section", async () => {
    renderPage();
    await screen.findAllByRole("row");
    const log = screen.getByRole("heading", { level: 2, name: "This season" }).closest("section");
    expect(log?.textContent).not.toMatch(/projection|proj|floor|ceiling/i);
  });
});
