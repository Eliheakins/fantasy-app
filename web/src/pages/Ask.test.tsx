import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import Ask from "./Ask";
import { fetchManifest } from "@/stat/lib/api";
import { getPlayerDictionary } from "@/stat/lib/players";
import { FIXTURE_SEASONS } from "@/stat/testing/seasons";

vi.mock("@/stat/lib/api", () => ({ fetchManifest: vi.fn() }));
vi.mock("@/stat/lib/players", () => ({ getPlayerDictionary: vi.fn(), getPlayersByIds: vi.fn(async () => []) }));
// The results table is the engine's business (Explore tests); here only Ask's own flow is under test.
vi.mock("@/features/explore/ExploreResultsCanvas", () => ({ ExploreResultsCanvas: () => null }));
vi.mock("@/features/explore/useExploreQueryExecution", () => ({
  useExploreQueryExecution: () => ({ result: null, error: null, details: null, running: false, pinnedPlayers: [], namedPlayers: [] }),
}));

const MAHOMES = { gsis_id: "00-0033873", display_name: "Patrick Mahomes", search_key: "patrick mahomes", position: "QB", team: "KC" };

function Where() {
  const { pathname, search } = useLocation();
  return <p data-testid="where">{pathname + search}</p>;
}

function renderAsk(entry = "/ask?league=a&team=2") {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={[entry]}>
        <Ask />
        <Where />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function ask(question: string) {
  await userEvent.type(await screen.findByRole("textbox", { name: "Question" }), question);
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
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
  vi.mocked(getPlayerDictionary).mockResolvedValue([MAHOMES]);
});
afterEach(() => vi.unstubAllGlobals());

describe("Ask page", () => {
  it("answers a ranking with the rules when the intent endpoint is down, keeping league and team in the URL", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetchMock);
    renderAsk();

    await ask("who led the league in passing yards in 2023");

    await waitFor(() => expect(screen.getByTestId("where").textContent).toContain("q=who+led+the+league"));
    const where = new URL(screen.getByTestId("where").textContent ?? "", "http://x");
    expect(where.pathname).toBe("/ask");
    expect(where.searchParams.get("league")).toBe("a");
    expect(where.searchParams.get("team")).toBe("2");
    expect(where.searchParams.getAll("s")).toEqual(["pass_yards"]);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("explains that the Ask service is unreachable for a question only the model can read, instead of failing silently", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    renderAsk();

    await ask("Mahomes flurbnozzle in 2023");

    expect(await screen.findByRole("alert")).toHaveTextContent(/Ask service is not reachable/);
  });

  it("shows the model's unsupported reason as text, never as HTML", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ outcome: "unsupported", reason: "Not here <b>x</b> <img src=x onerror=alert(1)>" })),
    );
    renderAsk();

    await ask("Mahomes flurbnozzle in 2023");

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Not here <b>x</b> <img src=x onerror=alert(1)>");
    expect(alert.querySelector("b, img")).toBeNull();
  });

  it("keeps an alert region in the page so a message is announced, and limits the question to the backend's 2000 characters", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ outcome: "unsupported", reason: "No." })),
    );
    renderAsk();

    expect(await screen.findByRole("alert")).toBeEmptyDOMElement();
    expect(screen.getByRole("textbox", { name: "Question" })).toHaveAttribute("maxlength", "2000");
    await ask("Mahomes flurbnozzle in 2023");
    expect(screen.getByRole("alert")).toHaveTextContent("No.");
  });

  it("aborts the model request on unmount and writes nothing when the reply arrives anyway", async () => {
    let signal: AbortSignal | undefined;
    let reply: (r: Response) => void = () => undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, init: RequestInit) => {
        signal = init.signal ?? undefined;
        return new Promise<Response>((resolve) => (reply = resolve));
      }),
    );
    const view = renderAsk();
    await ask("Mahomes flurbnozzle in 2023");
    await waitFor(() => expect(signal).toBeDefined());

    view.unmount();
    expect(signal?.aborted).toBe(true);
    reply(Response.json({ outcome: "query", intent: { stat_ids: ["pass_yards"], filter_ids: [], granularity: "total" } }));
    await new Promise((r) => setTimeout(r, 20));

    expect(window.localStorage.length).toBe(0);
  });

  it("keeps the history as a tab inside Ask, with each ask logged", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Response.json({ outcome: "unsupported", reason: "No." })),
    );
    renderAsk();
    await ask("Mahomes flurbnozzle in 2023");
    await screen.findByRole("alert");

    await userEvent.click(screen.getByRole("tab", { name: "History" }));

    expect(await screen.findByText("Mahomes flurbnozzle in 2023")).toBeInTheDocument();
  });
});
