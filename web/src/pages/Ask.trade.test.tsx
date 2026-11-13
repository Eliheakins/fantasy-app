import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import Ask from "./Ask";
import { fetchManifest } from "@/stat/lib/api";
import { getPlayerDictionary } from "@/stat/lib/players";
import { FIXTURE_SEASONS } from "@/stat/testing/seasons";
import { type Call, okReply, stubApi } from "@/test/fakeApi";
import { renderWithProviders } from "@/test/render";

vi.mock("@/stat/lib/api", () => ({ fetchManifest: vi.fn() }));
vi.mock("@/stat/lib/players", () => ({ getPlayerDictionary: vi.fn(), getPlayersByIds: vi.fn(async () => []) }));
vi.mock("@/features/explore/ExploreResultsCanvas", () => ({ ExploreResultsCanvas: () => null }));
vi.mock("@/features/explore/useExploreQueryExecution", () => ({
  useExploreQueryExecution: () => ({ result: null, error: null, details: null, running: false, pinnedPlayers: [], namedPlayers: [] }),
}));

const player = (gsis_id: string, display_name: string, position = "TE") => ({
  gsis_id,
  display_name,
  search_key: display_name.toLowerCase(),
  position,
  team: "KC",
});
const side = (s: string, team_name: string, playoff_after: number) => ({
  side: s,
  roster_id: 1,
  team_name,
  playoff_before: 0.5,
  playoff_after,
  title_before: 0.1,
  title_after: 0.12,
  wins_before: 8,
  wins_after: 8.4,
});
const EVALUATION = {
  odds: [side("me", "My Team", 0.56), side("them", "Rivals", 0.45)],
  roster_changes: [],
  warning: null,
  trade_deadline: null,
  market: null,
};
const OWNERS = {
  rows: [
    { gsis_id: "kelce", owner: "My Team", roster_id: 1, is_mine: true },
    { gsis_id: "kittle", owner: "Rivals", roster_id: 7, is_mine: false },
    { gsis_id: "hill", owner: "Others", roster_id: 8, is_mine: false },
  ],
  unmatched: 0,
};
let evaluateReply: { status: string; data?: unknown; started_at?: string | null };
let calls: Call[] = [];

function renderAsk(entry: string) {
  renderWithProviders(<Ask />, { route: entry, league: true });
}

beforeEach(() => {
  window.localStorage.clear();
  evaluateReply = { status: "ok", data: EVALUATION };
  vi.mocked(fetchManifest).mockResolvedValue({
    schema_version: 1,
    built_at: "2026-11-04T12:00:00+00:00",
    nflreadpy_version: "0.1.0",
    seasons: FIXTURE_SEASONS.map((season) => ({ season, path: `p${season}.parquet`, rows: 1, max_week: 9, has_participation: true })),
    player_index: null,
    player_game: null,
    players: null,
  });
  vi.mocked(getPlayerDictionary).mockResolvedValue([
    player("kelce", "Travis Kelce"),
    player("kittle", "George Kittle"),
    player("hill", "Tyreek Hill", "WR"),
    player("free", "Free Agent"),
    player("kicker", "Kicker Kim", "K"),
    player("allen-qb", "Josh Allen", "QB"),
    player("allen-lb", "Josh Allen", "LB"),
  ]);
  calls = stubApi(({ url }) => {
    if (url === "/api/leagues/a/owners") return okReply(OWNERS);
    if (url === "/api/leagues") return okReply([{ league_key: "a", name: "A", current_week: 9 }]);
    if (url === "/api/leagues/a/lineup") return okReply([]); // a start/sit question reads it
    if (url !== "/api/leagues/a/trades/evaluate") return undefined;
    const { status, data = null, started_at = null } = evaluateReply;
    return { body: { status, data, error: null, started_at } };
  });
});

const callsTo = (part: string) => calls.filter(({ url }) => url.includes(part));

describe("Ask trade", () => {
  it("evaluates the trade with the owner as partner, posts the Trades page's body and header, and renders TradeResult", async () => {
    renderAsk("/ask?league=a&team=2&q=trade+Kelce+for+Kittle");

    expect(await screen.findByRole("region", { name: "My Team" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Rivals" })).toBeInTheDocument();
    expect(screen.getAllByText("Make playoffs").length).toBeGreaterThan(0);
    expect(callsTo("/trades/evaluate")).toEqual([
      { url: "/api/leagues/a/trades/evaluate", method: "POST", body: { partner_roster_id: 7, give_ids: ["kelce"], get_ids: ["kittle"] } },
    ]);
    const request = vi
      .mocked(fetch)
      .mock.calls.map(([input]) => input)
      .find((input) => input instanceof Request && input.method === "POST");
    expect(request instanceof Request && request.headers.get("X-Requested-With")).toBe("fantasy-app");
    expect(screen.getByRole("link", { name: /Trades page/ })).toHaveAttribute("href", "/moves?league=a&team=2&view=trades");
    expect(callsTo("/nlq/intent")).toHaveLength(0);
  });

  it("shows the busy envelope while the evaluation runs", async () => {
    evaluateReply = { status: "running", started_at: new Date(Date.now() - 12000).toISOString() };
    renderAsk("/ask?league=a&q=Kelce+for+Kittle+trade");

    expect(await screen.findByText(/1\d s so far/)).toBeInTheDocument();
  });

  it("hands off to /trades when the get side spans several teams, without evaluating", async () => {
    renderAsk("/ask?league=a&team=2&q=trade+Kelce+for+Kittle+and+Hill");

    expect(await screen.findByText(/different teams/)).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Trades page/ })[0]).toHaveAttribute("href", "/moves?league=a&team=2&view=trades");
    expect(callsTo("/trades/evaluate")).toHaveLength(0);
  });

  it("hands off for a free agent", async () => {
    renderAsk("/ask?league=a&q=trade+Kelce+for+Free+Agent");

    expect(await screen.findByText(/Free Agent is a free agent/)).toBeInTheDocument();
    expect(callsTo("/trades/evaluate")).toHaveLength(0);
  });

  it("states the change in odds in one sentence above the result", async () => {
    renderAsk("/ask?league=a&q=trade+Kelce+for+Kittle");

    expect(
      await screen.findByText("This trade raises your playoff odds by 6.0 points and your title odds by 2.0 points."),
    ).toBeInTheDocument();
  });

  it("says kickers are not supported rather than calling them free agents", async () => {
    renderAsk("/ask?league=a&q=trade+Kelce+for+Kicker+Kim");

    expect(await screen.findByText(/kickers and defenses are not supported/i)).toBeInTheDocument();
    expect(callsTo("/trades/evaluate")).toHaveLength(0);
  });

  it("does not ask for trade-partners any more", async () => {
    renderAsk("/ask?league=a&q=trade+Kelce+for+Kittle");
    await screen.findByRole("region", { name: "Rivals" });
    expect(callsTo("/trade-partners")).toHaveLength(0);
  });

  it("logs the ask to the history as a trade entry", async () => {
    renderAsk("/ask?league=a&q=trade+Kelce+for+Kittle");
    await screen.findByRole("region", { name: "Rivals" });

    await userEvent.click(screen.getByRole("tab", { name: "History" }));

    expect(await screen.findByText(/Trade: Travis Kelce for George Kittle/)).toBeInTheDocument();
  });

  it("asks which player for a namesake, then answers", async () => {
    renderAsk("/ask?league=a&q=trade+Josh+Allen+for+Kittle");

    await userEvent.click(await screen.findByRole("button", { name: /Josh Allen · QB/ }));

    expect(await screen.findByText(/Josh Allen is not on this team's roster/)).toBeInTheDocument();
    expect(callsTo("/nlq/intent")).toHaveLength(0);
  });

  it("leaves stat and start/sit questions to their paths", async () => {
    renderAsk("/ask?league=a&q=start+Kelce+or+Kittle");
    await screen.findByRole("region", { name: "Start or sit" });
    expect(screen.queryByRole("region", { name: "Trade" })).toBeNull();
  });
});
