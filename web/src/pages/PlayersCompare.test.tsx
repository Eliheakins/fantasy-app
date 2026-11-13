import userEvent from "@testing-library/user-event";
import { screen, within } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { ApiState } from "@/api/envelope";
import { useEnvelopeQuery } from "@/api/useEnvelope";
import { TeamContext } from "@/lib/teamContext";
import { fetchManifest } from "@/stat/lib/api";
import { getPlayers, getPlayersByIds } from "@/stat/lib/players";
import PlayersCompare from "./PlayersCompare";
import { renderWithProviders } from "@/test/render";

vi.mock("@/api/useEnvelope", () => ({ useEnvelopeQuery: vi.fn() }));
vi.mock("@/stat/lib/api", () => ({ fetchManifest: vi.fn() }));
vi.mock("@/stat/lib/players", async (orig) => ({
  ...(await orig<typeof import("@/stat/lib/players")>()),
  getPlayers: vi.fn(),
  getPlayersByIds: vi.fn(),
}));

const PEOPLE = [
  { gsis_id: "a", full_name: "Ann Alpha", position: "WR", team: "KC", headshot_url: null },
  { gsis_id: "b", full_name: "Bob Beta", position: "RB", team: "BUF", headshot_url: null },
  { gsis_id: "c", full_name: "Cy Gamma", position: "TE", team: "SF", headshot_url: null },
  { gsis_id: "d", full_name: "Dee Delta", position: "QB", team: "DAL", headshot_url: null },
];
const profileOf = (id: string) => ({
  gsis_id: id,
  full_name: id,
  position: "WR",
  week: 9,
  result_week: null,
  result_points: null,
  is_out: false,
  projection: 10,
  p10: 4,
  median: 10,
  p90: 20,
  chance_to_play: 1,
  injury: null,
  injury_note: null,
  ros_points: 50,
  replacement_name: "Free Guy",
  replacement_points: 40,
  ros_over_replacement: 10,
  outlook_label: null,
  why: null,
  role_weeks: [],
});
const ready = <T,>(data: T): ApiState<T> => ({ kind: "ready", data }) as ApiState<T>;

beforeEach(() => {
  vi.mocked(fetchManifest).mockResolvedValue({ built_at: "t" } as never);
  vi.mocked(getPlayers).mockResolvedValue(PEOPLE as never);
  vi.mocked(getPlayersByIds).mockImplementation((async (_m: unknown, ids: string[]) =>
    PEOPLE.filter((p) => ids.includes(p.gsis_id))) as never);
  vi.mocked(useEnvelopeQuery).mockImplementation(((path: string | null) => {
    const hit = path?.match(/players\/([^/]+)\/profile/);
    if (hit) return ready(profileOf(decodeURIComponent(hit[1] ?? "")));
    return path?.includes("/market-values")
      ? ready([])
      : path?.includes("/owners")
        ? ready({ rows: [], unmatched: 0 })
        : { kind: "loading" };
  }) as typeof useEnvelopeQuery);
});
afterEach(() => vi.resetAllMocks());

function renderAt(entry: string) {
  const router = createMemoryRouter([{ path: "/players/compare", element: <PlayersCompare /> }], { initialEntries: [entry] });
  renderWithProviders(
    <TeamContext.Provider
      value={{ team: 2, league: "a", teams: [], viewed: null, setTeam: () => {}, notice: null, dismissNotice: () => {} }}
    >
      <RouterProvider router={router} />
    </TeamContext.Provider>,
  );
  return router;
}

describe("Players compare", () => {
  it("shows one column per player with the same sections, stacked on a phone and side by side from md up", async () => {
    renderAt("/players/compare?league=a&p=a&p=b");
    expect(screen.getByRole("heading", { level: 1, name: "Compare players" })).toBeInTheDocument();
    await screen.findByRole("group", { name: "Bob Beta" });
    const columns = screen.getAllByRole("group");
    expect(columns.map((c) => c.getAttribute("aria-label"))).toEqual(["Ann Alpha", "Bob Beta"]);
    for (const col of columns) {
      expect(within(col).getByRole("heading", { level: 3, name: "Next game" })).toBeInTheDocument();
      expect(within(col).getByRole("heading", { level: 3, name: "Rest of season" })).toBeInTheDocument();
    }
    const grid = columns[0]!.parentElement!;
    expect(grid.className).toMatch(/grid-cols-1/);
    expect(grid.className).toMatch(/md:grid-cols-2/);
  });

  it("uses three columns for three players and links each name to its page", async () => {
    renderAt("/players/compare?p=a&p=b&p=c");
    await screen.findByRole("group", { name: "Cy Gamma" });
    const columns = screen.getAllByRole("group");
    expect(columns).toHaveLength(3);
    expect(columns[0]!.parentElement!.className).toMatch(/md:grid-cols-3/);
    expect(within(columns[2]!).getByRole("link", { name: "Cy Gamma" })).toHaveAttribute("href", "/players/c");
  });

  it("asks for players when none are chosen", () => {
    renderAt("/players/compare");
    expect(screen.getByText(/pick two or three players/i)).toBeInTheDocument();
  });

  it("removes a player, keeping league, team and the others in the URL", async () => {
    const router = renderAt("/players/compare?league=a&team=2&p=a&p=b");
    await userEvent.setup().click(await screen.findByRole("button", { name: "Remove Ann Alpha" }));
    expect(router.state.location.search).toBe("?league=a&team=2&p=b");
  });

  it("adds a player from the search and stops offering search at three players", async () => {
    const user = userEvent.setup();
    const router = renderAt("/players/compare?league=a&p=a&p=b");
    await user.type(screen.getByLabelText("Add a player"), "Cy");
    await user.click(await screen.findByRole("button", { name: /Cy Gamma/ }));
    expect(router.state.location.search).toBe("?league=a&p=a&p=b&p=c");
    expect(await screen.findAllByRole("group")).toHaveLength(3);
    expect(screen.queryByLabelText("Add a player")).toBeNull();
  });

  it("rewrites duplicate, blank and extra ids in the URL with replace", async () => {
    const router = renderAt("/players/compare?league=a&p=a&p=a&p=&p=b&p=c&p=d");
    await screen.findByRole("group", { name: "Cy Gamma" });
    expect(router.state.location.search).toBe("?league=a&p=a&p=b&p=c");
    expect(screen.getAllByRole("group")).toHaveLength(3);
    expect(router.state.historyAction).toBe("REPLACE");
  });

  it("shows an unknown id as Player not found with Remove, and makes no profile request for it", async () => {
    const router = renderAt("/players/compare?p=a&p=zzz");
    const column = await screen.findByRole("group", { name: "Player not found" });
    expect(within(column).getByText(/zzz/)).toBeInTheDocument();
    expect(vi.mocked(useEnvelopeQuery).mock.calls.some(([path]) => String(path).includes("/zzz/"))).toBe(false);
    await userEvent.setup().click(within(column).getByRole("button", { name: "Remove Player not found" }));
    expect(router.state.location.search).toBe("?p=a");
  });

  it("has one h1, each player an h2 and their sections h3", async () => {
    renderAt("/players/compare?p=a&p=b");
    await screen.findByRole("group", { name: "Bob Beta" });
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent)).toEqual(["Side by side", "Ann Alpha", "Bob Beta"]);
    expect(screen.getAllByRole("heading", { level: 3 }).length).toBe(10);
  });

  it("tells the search result count and when nothing matches", async () => {
    const user = userEvent.setup();
    renderAt("/players/compare?p=a");
    await user.type(screen.getByLabelText("Add a player"), "Cy");
    expect(await screen.findByText("1 player found.")).toBeInTheDocument();
    vi.mocked(getPlayers).mockResolvedValue([] as never);
    await user.type(screen.getByLabelText("Add a player"), "x");
    expect(await screen.findByText("No players match.")).toBeInTheDocument();
  });
});
