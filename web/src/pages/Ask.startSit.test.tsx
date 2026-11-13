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
const lineupRow = (id: string, projection: number, recommended = true) => ({
  slot: "TE",
  gsis_id: id,
  full_name: id,
  position: "TE",
  projection,
  p10: projection - 5,
  p90: projection + 6,
  starting_now: true,
  recommended,
  injury: null,
  injury_note: null,
  locked: false,
  actual: 0,
  game: "Sun",
  change: "",
});
let calls: Call[] = [];

function renderAsk(entry: string) {
  renderWithProviders(<Ask />, { route: entry, league: true });
}

beforeEach(() => {
  window.localStorage.clear();
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
    player("allen-qb", "Josh Allen", "QB"),
    player("allen-lb", "Josh Allen", "LB"),
  ]);
  calls = stubApi(({ url }) =>
    url.startsWith("/api/leagues/a/lineup")
      ? okReply([lineupRow("kelce", 9, false), lineupRow("kittle", 12.5, true)])
      : url === "/api/leagues"
        ? okReply([{ league_key: "a", name: "A", current_week: 9 }])
        : undefined,
  );
});

const modelCalls = () => calls.filter(({ url }) => url.includes("/nlq/intent"));

describe("Ask start/sit", () => {
  it("answers on arrival from /ask?q= with the lineup comparison and never calls the model", async () => {
    renderAsk("/ask?league=a&team=2&q=should+I+start+Kelce+or+Kittle");

    expect(await screen.findByText("Start George Kittle over Travis Kelce")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Lineup page/ })).toHaveAttribute("href", "/lineup?league=a&team=2");
    expect(modelCalls()).toHaveLength(0);
  });

  it("logs the ask to the history as a start/sit entry", async () => {
    renderAsk("/ask?league=a&q=start+Kelce+or+Kittle");
    await screen.findByText("Start George Kittle over Travis Kelce");

    await userEvent.click(screen.getByRole("tab", { name: "History" }));

    expect(await screen.findByText("start Kelce or Kittle")).toBeInTheDocument();
    expect(screen.getByText(/Start\/sit: Travis Kelce or George Kittle/)).toBeInTheDocument();
  });

  it("answers from its own box, and puts the question in the URL", async () => {
    renderAsk("/ask?league=a");
    await userEvent.type(await screen.findByRole("textbox", { name: "Question" }), "Kelce or Kittle this week");
    await userEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect(await screen.findByText("Start George Kittle over Travis Kelce")).toBeInTheDocument();
    expect(modelCalls()).toHaveLength(0);
  });

  it("asks which player for a namesake, then answers", async () => {
    vi.mocked(getPlayerDictionary).mockResolvedValue([
      player("kelce", "Travis Kelce"),
      player("allen-qb", "Josh Allen", "QB"),
      player("allen-lb", "Josh Allen", "LB"),
    ]);
    renderAsk("/ask?league=a&q=start+Josh+Allen+or+Kelce");

    await userEvent.click(await screen.findByRole("button", { name: /Josh Allen · QB/ }));

    expect(await screen.findByText(/Josh Allen is not on this team's roster/)).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Start or sit" })).toBeInTheDocument();
    expect(modelCalls()).toHaveLength(0);
  });

  it("names an unknown player instead of asking the model", async () => {
    renderAsk("/ask?league=a&q=start+Kelce+or+Nobodyson");

    expect(await screen.findByRole("alert")).toHaveTextContent(/Nobodyson/);
    expect(modelCalls()).toHaveLength(0);
  });
});
