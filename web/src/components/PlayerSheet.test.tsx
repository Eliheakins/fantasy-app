import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useNavigate } from "react-router-dom";
import type { ApiState } from "@/api/envelope";
import { useApi } from "@/hooks/useApi";
import { TeamContext } from "@/lib/teamContext";
import { runStatQuery } from "@/stat/engine/statQuery";
import { fetchManifest } from "@/stat/lib/api";
import { getPlayersByIds } from "@/stat/lib/players";
import { PlayerLink } from "./PlayerLink";

vi.mock("@/hooks/useApi", () => ({ useApi: vi.fn() }));
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

function mockApi(points: ApiState<unknown>, owners: ApiState<unknown> = ready({ rows: [{ gsis_id: "00-1", owner: "Lisan Al-Caleb", is_mine: true }], unmatched: 0 })) {
  vi.mocked(useApi).mockImplementation(((path: string | null) =>
    path?.includes("/player-points") ? points : path?.includes("/owners") ? owners : { kind: "loading" }) as typeof useApi);
}

function renderLink(entry = "/lineup?league=a&team=2&x=1") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <TeamContext.Provider value={{ team: 2, league: "a", teams: [], viewed: null, setTeam: () => {}, notice: null, dismissNotice: () => {} }}>
        <MemoryRouter initialEntries={[entry]}>
          <PlayerLink gsisId="00-1" name="Ja'Marr Chase" position="WR" />
        </MemoryRouter>
      </TeamContext.Provider>
    </QueryClientProvider>,
  );
}

const open = async () => {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Ja'Marr Chase, open stats" }));
  return { user, dialog: await screen.findByRole("dialog", { name: "Ja'Marr Chase" }) };
};

beforeEach(() => {
  vi.mocked(fetchManifest).mockResolvedValue(manifest as never);
  vi.mocked(runStatQuery).mockResolvedValue(gameLog as never);
  vi.mocked(getPlayersByIds).mockResolvedValue([{ gsis_id: "00-1", full_name: "Ja'Marr Chase", position: "WR", team: "CIN", headshot_url: null }] as never);
  mockApi(ready([{ week: 1, points: 21.1 }, { week: 2, points: 12.4 }]));
});
afterEach(() => vi.resetAllMocks());

describe("PlayerSheet", () => {
  it("opens with the name as title, the header, the game log rows and league points by week", async () => {
    renderLink();
    const { dialog } = await open();
    expect(await within(dialog).findByText("CIN")).toBeInTheDocument();
    expect(within(dialog).getByText("WR")).toBeInTheDocument();
    expect(within(dialog).getByText(/Lisan Al-Caleb/)).toBeInTheDocument();
    const rows = await within(dialog).findAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(within(rows[1]!).getAllByRole("cell").map((c) => c.textContent)).toEqual(["1", "7", "101", "21.1"]);
    expect(within(rows[2]!).getAllByRole("cell").map((c) => c.textContent)).toEqual(["2", "5", "64", "12.4"]);
    expect(vi.mocked(runStatQuery).mock.calls[0]![0]).toMatchObject({
      statIds: ["rec_receptions", "rec_yards"], gsisIds: ["00-1"], split: "week", granularity: "total",
      filterChipState: { "season-2026": true, "stype-reg": true },
    });
  });

  it("shows a Callout and keeps league points when the engine fails", async () => {
    vi.mocked(runStatQuery).mockRejectedValue(new Error("shard missing"));
    renderLink();
    const { dialog } = await open();
    expect(await within(dialog).findByText(/shard missing/)).toBeInTheDocument();
    expect(within(dialog).getByText("21.1")).toBeInTheDocument();
  });

  it("shows a Callout and keeps league points when the manifest fails", async () => {
    vi.mocked(fetchManifest).mockRejectedValue(new Error("no manifest"));
    renderLink();
    const { dialog } = await open();
    expect(await within(dialog).findByText(/no manifest/)).toBeInTheDocument();
    expect(within(dialog).getByText("12.4")).toBeInTheDocument();
  });

  it("keeps the game log when the league points fail", async () => {
    mockApi(failed);
    renderLink();
    const { dialog } = await open();
    expect(await within(dialog).findByText("101")).toBeInTheDocument();
    expect(within(dialog).getByText(/league points did not load: boom/i)).toBeInTheDocument();
  });

  it("does not claim there are no games when the game log failed", async () => {
    vi.mocked(runStatQuery).mockRejectedValue(new Error("shard missing"));
    mockApi(ready([]));
    renderLink();
    const { dialog } = await open();
    expect(await within(dialog).findByText(/shard missing/)).toBeInTheDocument();
    expect(within(dialog).queryByText(/no games this season/i)).toBeNull();
  });

  it("closes when the league or team in the URL changes", async () => {
    function Switch() {
      const navigate = useNavigate();
      return <button onClick={() => navigate("/lineup?league=b")}>switch league</button>;
    }
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={["/lineup?league=a"]}>
          <PlayerLink gsisId="00-1" name="Ja'Marr Chase" position="WR" />
          <Switch />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Ja'Marr Chase, open stats" }));
    await screen.findByRole("dialog");
    fireEvent.click(screen.getByRole("button", { name: "switch league", hidden: true })); // the modal blocks pointer events outside it
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("closes on Escape and returns focus to the name that opened it", async () => {
    renderLink();
    const { user } = await open();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Ja'Marr Chase, open stats" })).toHaveFocus();
  });

  it("Open in Explore keeps league and team, and closes the sheet", async () => {
    renderLink();
    const { user, dialog } = await open();
    const link = within(dialog).getByRole("link", { name: /open in explore/i });
    const href = new URL(link.getAttribute("href") ?? "", "http://x");
    expect(href.pathname).toBe("/explore");
    expect(href.searchParams.get("p")).toBe("00-1");
    expect(href.searchParams.get("league")).toBe("a");
    expect(href.searchParams.get("team")).toBe("2");
    await user.click(link);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("has no projection wording anywhere in the sheet", async () => {
    renderLink();
    const { dialog } = await open();
    await within(dialog).findAllByRole("row");
    expect(dialog.textContent).not.toMatch(/projection|proj|floor|ceiling/i);
  });
});
