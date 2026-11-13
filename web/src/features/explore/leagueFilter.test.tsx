import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useLocation } from "react-router";

import { LeagueProvider } from "@/lib/league";
import { TeamProvider } from "@/lib/TeamProvider";
import { useTeam } from "@/lib/teamContext";
import { runStatQuery } from "@/stat/engine/statQuery";

import { ExploreResultsCanvas } from "./ExploreResultsCanvas";
import { LeagueFilterControl } from "./LeagueFilterControl";
import { ManifestContext } from "@/stat/react/manifest";
import { useExploreQueryExecution } from "./useExploreQueryExecution";
import { type Reply, stubApi } from "@/test/fakeApi";
import { renderWithProviders } from "@/test/render";

vi.mock("@/stat/engine/statQuery", () => ({
  runStatQuery: vi.fn(async () => ({ columns: ["player_id"], rows: [] })),
}));
const { sources } = vi.hoisted(() => ({
  sources: {
    current: [
      { year: 2024, url: "mem://2024" },
      { year: 2025, url: "mem://2025" },
    ],
  },
}));
vi.mock("@/stat/lib/dataSources", () => ({
  seasonSources: () => sources.current,
  playerGameSource: () => null,
  playerIndexSource: () => null,
}));
vi.mock("@/stat/lib/players", () => ({ getPlayersByIds: async () => [] }));

const ok = (data: unknown) => ({ status: "ok", data, error: null, started_at: null });
const owner = (gsis_id: string, name: string, is_mine: boolean) => ({ gsis_id, owner: name, is_mine });
const team = (roster_id: number, team_name: string, is_me: boolean) => ({
  roster_id,
  team_name,
  is_me,
  wins: 1,
  losses: 0,
  ties: 0,
  points_for: 10,
  record: "1-0",
});
const MINE = [owner("00-A", "Mine", true), owner("00-B", "Rival", false)];
const RIVAL_VIEW = [owner("00-A", "Mine", false), owner("00-B", "Rival", true)];

function mockFetch(leagues: unknown[] = [{ league_key: "a", name: "A" }], unmatched = 0) {
  const urls: string[] = [];
  stubApi(({ url }) => {
    urls.push(url);
    const [path = "", query = ""] = url.split("?");
    const routes: Record<string, unknown> = {
      "/api/leagues": leagues,
      "/api/leagues/a/teams": [team(1, "Mine", true), team(2, "Rival", false)],
      "/api/leagues/a/player-points": [{ gsis_id: "00-A", week: 1, points: 12.5 }],
      "/api/leagues/a/owners": { rows: query.includes("team=2") ? RIVAL_VIEW : MINE, unmatched },
    };
    return path in routes ? { body: ok(routes[path]) } : undefined;
  });
  return urls;
}

function renderAt(entry: string, children: React.ReactNode) {
  renderWithProviders(
    <ManifestContext.Provider value={{ manifest: null, seasons: [2025] }}>
      <LeagueProvider>
        <TeamProvider>{children}</TeamProvider>
      </LeagueProvider>
    </ManifestContext.Provider>,
    { route: entry },
  );
}

function Search() {
  return <p data-testid="search">{useLocation().search}</p>;
}

const search = () => new URLSearchParams(screen.getByTestId("search").textContent ?? "");

beforeEach(() => {
  localStorage.clear();
  vi.mocked(runStatQuery).mockClear();
});

describe("League filter control", () => {
  it("is hidden when no league is loaded", async () => {
    const urls = mockFetch([]);
    renderAt("/explore?lg=fa", <LeagueFilterControl />);
    await waitFor(() => expect(urls).toContain("/api/leagues"));

    expect(screen.queryByRole("radiogroup", { name: "League" })).not.toBeInTheDocument();
  });

  it("is hidden for team rows", async () => {
    mockFetch();
    renderAt("/explore?who=teams", <LeagueFilterControl />);
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());

    expect(screen.queryByRole("radiogroup", { name: "League" })).not.toBeInTheDocument();
  });

  it("warns when rostered players could not be matched", async () => {
    mockFetch([{ league_key: "a", name: "A" }], 2);
    renderAt("/explore", <LeagueFilterControl />);

    expect(await screen.findByText(/2 rostered players could not be matched and may appear as free agents/)).toBeInTheDocument();
  });

  it("shows no warning when every rostered player matched", async () => {
    const urls = mockFetch();
    renderAt("/explore", <LeagueFilterControl />);
    await screen.findByRole("radiogroup", { name: "League" });
    await waitFor(() => expect(urls).toContain("/api/leagues/a/owners"));
    expect(screen.queryByText(/could not be matched/)).not.toBeInTheDocument();
  });

  it("says the rosters are today's and writes lg to the URL", async () => {
    mockFetch();
    renderAt(
      "/explore?s=rec_yards",
      <>
        <LeagueFilterControl />
        <Search />
      </>,
    );

    await userEvent.click(await screen.findByRole("radio", { name: "Free agents now" }));

    expect(search().get("lg")).toBe("fa");
    expect(search().getAll("s")).toEqual(["rec_yards"]);
    await userEvent.click(screen.getByRole("radio", { name: "All players" }));
    expect(search().has("lg")).toBe(false);
  });
});

function Run() {
  const { setTeam } = useTeam();
  const { result } = useExploreQueryExecution();
  return (
    <>
      <button type="button" onClick={() => setTeam(2)}>
        view rival
      </button>
      <Search />
      <ul>
        {result?.rows.map((r) => (
          <li key={String(r.player_id)}>{`row ${r.player_id}`}</li>
        ))}
      </ul>
    </>
  );
}

const lastSet = () => vi.mocked(runStatQuery).mock.calls.at(-1)?.[0].playerSet;
const RANKED = "/explore?league=a&s=rec_yards&o=rec_yards&n=5";

describe("League filter in the query", () => {
  it("restricts the engine to the roster set and recomputes it when the team changes", async () => {
    mockFetch();
    renderAt(`${RANKED}&lg=mine`, <Run />);

    await waitFor(() => expect(lastSet()).toEqual({ ids: ["00-A"], exclude: false }));
    await userEvent.click(screen.getByRole("button", { name: "view rival" }));

    await waitFor(() => expect(lastSet()).toEqual({ ids: ["00-B"], exclude: false }));
  });

  it("never shows the previous team's rows after a team switch", async () => {
    mockFetch();
    vi.mocked(runStatQuery).mockImplementation(async (params) => ({
      columns: ["player_id"],
      rows: (params.playerSet?.ids ?? []).map((player_id) => ({ player_id })),
    }));
    renderAt(`${RANKED}&lg=mine`, <Run />);
    await screen.findByText("row 00-A");

    await userEvent.click(screen.getByRole("button", { name: "view rival" }));

    expect(screen.queryByText("row 00-A")).not.toBeInTheDocument();
    await screen.findByText("row 00-B");
    expect(screen.queryByText("row 00-A")).not.toBeInTheDocument();
    vi.mocked(runStatQuery).mockImplementation(async () => ({ columns: ["player_id"], rows: [] }));
  });

  it("drops lg from the URL when no league exists or the rows are teams", async () => {
    mockFetch([]);
    renderAt(`${RANKED}&lg=fa`, <Run />);
    await waitFor(() => expect(search().has("lg")).toBe(false));
  });

  it("drops lg from the URL for team rows", async () => {
    mockFetch();
    renderAt("/explore?league=a&who=teams&s=rec_yards&lg=fa", <Run />);
    await waitFor(() => expect(search().has("lg")).toBe(false));
  });

  it("excludes every rostered player for free agents, and sends no set for All players", async () => {
    mockFetch();
    renderAt(`${RANKED}&lg=fa`, <Run />);
    await waitFor(() => expect(lastSet()).toEqual({ ids: ["00-A", "00-B"], exclude: true }));
  });

  it("ignores a bad lg value", async () => {
    mockFetch();
    renderAt(`${RANKED}&lg=nope`, <Run />);
    await waitFor(() => expect(runStatQuery).toHaveBeenCalled());
    expect(lastSet()).toBeNull();
  });

  it("does not run an unrestricted query while the rosters are loading", async () => {
    stubApi(({ url }) => {
      if (url.includes("/owners")) return new Promise<Reply>(() => {});
      if (url === "/api/leagues/a/teams") return { body: ok([team(1, "Mine", true)]) };
      return url === "/api/leagues" ? { body: ok([{ league_key: "a", name: "A" }]) } : undefined;
    });
    renderAt(`${RANKED}&lg=mine`, <Run />);
    await new Promise((r) => setTimeout(r, 30));
    expect(runStatQuery).not.toHaveBeenCalled();
  });
});

describe("owner on result rows", () => {
  const result = {
    columns: ["player_id", "m_rec_yards"],
    rows: [
      { player_id: "00-A", m_rec_yards: 10 },
      { player_id: "00-FA", m_rec_yards: 5 },
    ],
  };
  const names = [
    { gsis_id: "00-A", full_name: "Ann", position: "WR", team: null, headshot_url: null, birth_date: null, years_exp: null },
    { gsis_id: "00-FA", full_name: "Fay", position: "WR", team: null, headshot_url: null, birth_date: null, years_exp: null },
  ];

  it("shows the owning team for a rostered player and a Free agent marker for a free agent", async () => {
    mockFetch();
    renderAt(
      "/explore?league=a&s=rec_yards&o=rec_yards&n=5",
      <ExploreResultsCanvas result={result} error={null} details={null} running={false} pinnedPlayers={names} />,
    );

    const owner = await screen.findByText("Mine");
    expect(owner).toHaveClass("text-muted");
    expect(screen.getByText("Ann").closest("tr")!.textContent).toContain("Ann, owned by Mine"); // separator for screen readers
    const faRow = screen.getByText("Fay").closest("tr")!;
    expect(faRow.textContent).toContain("Free agent");
    expect(faRow.textContent).not.toContain("owned by");
  });
});

describe("League points fetch cost", () => {
  const pointUrls = (urls: string[]) => urls.filter((u) => u.includes("player-points"));

  it("fetches only the latest season when no season is chosen, and says so", async () => {
    const urls = mockFetch();
    vi.mocked(runStatQuery).mockResolvedValue({ columns: ["player_id"], rows: [] });
    renderAt("/explore?league=a&s=league_pts&o=league_pts&n=5", <RunWithCanvas />);

    await waitFor(() => expect(runStatQuery).toHaveBeenCalled());
    expect(pointUrls(urls)).toEqual(["/api/leagues/a/player-points?season=2025"]);
    expect(
      vi
        .mocked(runStatQuery)
        .mock.calls.at(-1)?.[0]
        .leaguePoints?.every((r) => r.season === 2025),
    ).toBe(true);
    expect((await screen.findByText(/only the latest season \(2025\)/)).textContent).toMatch(/pick seasons/i);
  });

  it("fetches every season for a split by season, and the chosen seasons otherwise", async () => {
    const urls = mockFetch();
    renderAt("/explore?league=a&s=league_pts&o=league_pts&n=5&by=season", <Run />);
    await waitFor(() => expect(pointUrls(urls)).toHaveLength(2));
    expect(pointUrls(urls).sort()).toEqual(["/api/leagues/a/player-points?season=2024", "/api/leagues/a/player-points?season=2025"]);
  });

  it("asks per pinned player instead of for everyone", async () => {
    const urls = mockFetch();
    renderAt("/explore?league=a&s=league_pts&p=00-A", <Run />);

    await waitFor(() => expect(pointUrls(urls)).toHaveLength(1));
    expect(pointUrls(urls)).toEqual(["/api/leagues/a/player-points?season=2025&gsis_id=00-A"]);
  });

  it("does not hang or fetch when the data has no seasons", async () => {
    const urls = mockFetch();
    sources.current = [];
    try {
      renderAt("/explore?league=a&s=league_pts&p=00-A", <RunWithCanvas />);
      await waitFor(() => expect(urls).toContain("/api/leagues"));
      await new Promise((r) => setTimeout(r, 50));
      expect(pointUrls(urls)).toEqual([]);
      expect(runStatQuery).not.toHaveBeenCalled();
      expect(screen.queryByText("Updating…")).toBeNull();
    } finally {
      sources.current = [
        { year: 2024, url: "mem://2024" },
        { year: 2025, url: "mem://2025" },
      ];
    }
  });
});

describe("League points in the query", () => {
  afterEach(() => vi.mocked(runStatQuery).mockImplementation(async () => ({ columns: ["player_id"], rows: [] })));
  const lastPoints = () => vi.mocked(runStatQuery).mock.calls.at(-1)?.[0].leaguePoints;

  it("fetches the league's weekly points for the season and hands them to the engine", async () => {
    const urls = mockFetch();
    renderAt("/explore?league=a&s=league_pts&o=league_pts&n=5", <Run />);

    await waitFor(() => expect(lastPoints()).toEqual([{ gsis_id: "00-A", week: 1, points: 12.5, season: 2025 }]));
    expect(urls).toContain("/api/leagues/a/player-points?season=2025");
  });

  it("does not fetch points for a query without a league stat", async () => {
    const urls = mockFetch();
    renderAt(RANKED, <Run />);

    await waitFor(() => expect(runStatQuery).toHaveBeenCalled());
    expect(urls.some((u) => u.includes("player-points"))).toBe(false);
    expect(lastPoints()).toBeNull();
  });

  it("shows the engine's no-league message when no league is picked", async () => {
    mockFetch([]);
    vi.mocked(runStatQuery).mockRejectedValueOnce(new Error("Pick a league first."));
    renderAt("/explore?s=league_pts&o=league_pts&n=5", <RunWithCanvas />);

    expect(await screen.findByText("Pick a league first.")).toBeTruthy();
    expect(vi.mocked(runStatQuery).mock.calls.at(-1)?.[0].leaguePoints).toBeNull();
  });

  it("names the selected league in the column header and the chip, and the engine got no league name", async () => {
    mockFetch();
    vi.mocked(runStatQuery).mockResolvedValue({
      columns: ["player_id", "m_league_pts"],
      rows: [{ player_id: "00-A", m_league_pts: 12.5 }],
    });
    renderAt("/explore?league=a&s=league_pts&p=00-A", <RunWithCanvas />);

    expect(await screen.findByText("League points (A) (per game)")).toBeTruthy();
    expect(JSON.stringify(vi.mocked(runStatQuery).mock.calls.at(-1)?.[0].statIds)).toBe('["league_pts"]');
  });

  it("shows the engine's notices above the table", async () => {
    mockFetch();
    vi.mocked(runStatQuery).mockResolvedValue({ columns: ["player_id"], rows: [], notices: ["Down filters cannot apply."] });
    renderAt("/explore?league=a&s=league_pts&o=league_pts&n=5", <RunWithCanvas />);

    expect(await screen.findByText("Down filters cannot apply.")).toBeTruthy();
  });
});

function RunWithCanvas() {
  const run = useExploreQueryExecution();
  return <ExploreResultsCanvas {...run} />;
}
