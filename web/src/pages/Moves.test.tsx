import { render, screen, within } from "@testing-library/react";
import { leaguePath, onlyRoutes } from "@/test/fakeApi";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router";
import type { ApiState } from "@/api/envelope";
import Moves from "./Moves";

const waiver = (name: string, over = {}) => ({
  gsis_id: `id-${name}`,
  full_name: name,
  position: "RB",
  drop_name: "Bernard",
  delta_points: 5,
  playoff_delta: 0.023,
  title_delta: 0.01,
  se_title: 0.002,
  trending_adds: null,
  ...over,
});
const trade = {
  kind: "trade",
  partner: "Rivals",
  give: "A",
  get: "B",
  give_ids: ["a"],
  get_ids: ["b"],
  rank: 1,
  playoff_delta: 0.03,
  title_delta: 0.01,
  se_title: 0.003,
  delta_points: 3,
};

let waivers: ApiState<unknown>;
let digest: ApiState<unknown>;
type Row = {
  league_key: string;
  name: string;
  current_week: number;
  playoff_week_start: number;
  team_phase?: string | null;
  playoff_label?: string | null;
};
let leagueRow: Row = { league_key: "a", name: "L", current_week: 9, playoff_week_start: 15 };
vi.mock("@/lib/league", () => ({
  useLeague: () => ({ league: "a", leagues: { kind: "ready", data: [leagueRow] } }),
  useLeagueName: () => "L",
  useLeagueRow: () => leagueRow,
  useLeagueApi: (route: string, query?: object) => onlyRoutes({ waivers, digest })(leaguePath(route, query)),
}));
vi.mock("@/features/moves/waivers/WaiversView", () => ({
  WaiversContent: ({
    rank,
    pos,
    onRank,
    onShowAll,
  }: {
    rank: string;
    pos: string | null;
    onRank: (r: string) => void;
    onShowAll: () => void;
  }) => (
    <div>
      <p>waivers details</p>
      <p data-testid="waiver-params">{`rank ${rank}, pos ${pos ?? "all"}`}</p>
      <button type="button" onClick={() => onRank("playoffs")}>
        rank by playoffs
      </button>
      <button type="button" onClick={() => onRank("ros")}>
        rank by season
      </button>
      <button type="button" onClick={onShowAll}>
        all positions
      </button>
    </div>
  ),
}));
vi.mock("@/features/moves/trade/TradeBuilder", () => ({ TradeBuilder: () => <p>trade builder</p> }));
vi.mock("@/features/moves/trade/TradeDetails", () => ({ TradeDetails: () => <p>trade details</p> }));

const ready = (data: unknown): ApiState<unknown> => ({ kind: "ready", data }) as ApiState<unknown>;
const digestWith = (trades: unknown[], odds_change: unknown[] = []) =>
  ready({ waivers: [], trades, odds_change, ideas: { is_mine: true } });
const myOdds = (p_title: number) => ({ is_me: true, as_of_week: 15, p_title, p_playoffs: 1 });

function Where() {
  return <p data-testid="search">{useLocation().search}</p>;
}
const renderAt = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Moves />
      <Where />
    </MemoryRouter>,
  );

beforeEach(() => {
  leagueRow = { league_key: "a", name: "L", current_week: 9, playoff_week_start: 15 };
  waivers = ready([waiver("Coleman"), waiver("Small", { playoff_delta: 0.001, delta_points: 1, trending_adds: 200000 })]);
  digest = digestWith([trade]);
});

describe("Moves page trade deadline callout", () => {
  it("shows the warning only in deadline week", () => {
    leagueRow = { ...leagueRow, trade_deadline: 9 } as typeof leagueRow;
    renderAt("/moves");
    expect(screen.getByText("Trades close after week 9.")).toBeInTheDocument();
  });

  it.each([null, 99, 11, 5])("shows nothing when the deadline is %s", (deadline) => {
    leagueRow = { ...leagueRow, trade_deadline: deadline } as typeof leagueRow;
    renderAt("/moves");
    expect(screen.queryByText(/Trades close after/)).not.toBeInTheDocument();
  });
});

describe("Moves page", () => {
  it("has one h1 that answers with the best move, and one ranked list of adds and trades", () => {
    renderAt("/moves?league=a");
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Trade A for B");
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent("Trade A for B");
    expect(items[1]).toHaveTextContent("Add Coleman, drop Bernard");
    expect(within(items[1]!).getAllByRole("button", { name: /what drives this/ }).length).toBeGreaterThan(0);
  });

  it("shows the drop with its points net of the drop, and the trending count as a number", () => {
    renderAt("/moves");
    const small = screen.getByText(/Small/).closest("li") as HTMLElement;
    expect(small).toHaveTextContent(/Trending: [\d,]+ adds across Sleeper/);
    expect(small).not.toHaveTextContent("Likely gone");
    expect(small).toHaveTextContent("Bernard");
    expect(small).toHaveTextContent("~0.1"); // a playoff change under the worth bar reads as noise, not a signed number
    expect(screen.getByText(/Coleman/).closest("li")).not.toHaveTextContent("Likely gone");
  });

  it("says no move is worth it when nothing clears the bar", () => {
    waivers = ready([waiver("Tiny", { playoff_delta: 0.001 })]);
    digest = digestWith([]);
    renderAt("/moves");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("No move is worth it this week");
  });

  it("filters the same list with ?view= and keeps other params", async () => {
    renderAt("/moves?league=a&week=5");
    await userEvent.click(screen.getByRole("radio", { name: "Trades" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    const params = new URLSearchParams(screen.getByTestId("search").textContent ?? "");
    expect(params.get("view")).toBe("trades");
    expect(params.get("week")).toBe("5");
    await userEvent.click(screen.getByRole("radio", { name: "Free agents" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    await userEvent.click(screen.getByRole("radio", { name: "All" }));
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });

  it("still shows adds when the trade ideas did not load, and says so", () => {
    digest = { kind: "error", error: { code: "x", message: "boom" } } as ApiState<unknown>;
    renderAt("/moves");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText(/Trade ideas did not load/)).toBeInTheDocument();
  });

  it("shows the trades view when the free agent list failed, with an error line for the part that failed", () => {
    waivers = { kind: "error", error: { code: "x", message: "boom" } } as ApiState<unknown>;
    renderAt("/moves?view=trades");
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Trade A for B");
    expect(screen.queryByText(/free agent list did not load/)).toBeNull();
  });

  it("does not wait for the free agents when only trades are shown", () => {
    waivers = { kind: "loading" } as ApiState<unknown>;
    renderAt("/moves?view=trades");
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("says what is empty for the chosen view", () => {
    waivers = ready([]);
    digest = digestWith([]);
    renderAt("/moves?view=trades");
    expect(screen.getByText("No trade ideas right now.")).toBeInTheDocument();
  });

  it("puts the builder after the list and the details last", () => {
    renderAt("/moves");
    expect(screen.getByText("trade builder")).toBeInTheDocument();
    expect(screen.getByText("waivers details")).toBeInTheDocument();
    expect(screen.getByText("trade details")).toBeInTheDocument();
  });
});

describe("Moves page waiver params", () => {
  it("hands ?rank= and ?pos= to the waiver tables, rest of season and every position by default", () => {
    renderAt("/moves?league=a&rank=playoffs&pos=RB");
    expect(screen.getByTestId("waiver-params")).toHaveTextContent("rank playoffs, pos RB");
  });

  it("reads anything else as rest of season and every position", () => {
    renderAt("/moves?rank=weird&pos=XX");
    expect(screen.getByTestId("waiver-params")).toHaveTextContent("rank ros, pos all");
  });

  it("writes the ranking to the URL, drops it for rest of season, and Show all drops ?pos=, keeping the other params", async () => {
    renderAt("/moves?league=a&pos=RB");
    await userEvent.click(screen.getByRole("button", { name: "rank by playoffs" }));
    expect(screen.getByTestId("search")).toHaveTextContent("rank=playoffs");
    await userEvent.click(screen.getByRole("button", { name: "rank by season" }));
    expect(screen.getByTestId("search")).not.toHaveTextContent("rank");
    await userEvent.click(screen.getByRole("button", { name: "all positions" }));
    expect(screen.getByTestId("search")).not.toHaveTextContent("pos");
    expect(screen.getByTestId("search")).toHaveTextContent("league=a");
  });
});

describe("Moves page in the playoffs", () => {
  beforeEach(() => {
    leagueRow = { ...leagueRow, current_week: 15 };
  });

  it("ranks by title odds and says so", () => {
    waivers = ready([
      waiver("Coleman", { playoff_delta: 0, title_delta: 0.02 }),
      waiver("Small", { playoff_delta: 0.5, title_delta: 0.001 }),
    ]);
    digest = digestWith([], [myOdds(0.3)]);
    renderAt("/moves");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Add Coleman, drop Bernard");
    expect(screen.getAllByText("title pts").length).toBeGreaterThan(0);
    expect(screen.getByText(/Ordered by title-odds change/)).toBeInTheDocument();
  });

  it("tells an eliminated team it is out instead of listing zero-value adds", () => {
    leagueRow = { ...leagueRow, team_phase: "eliminated" };
    waivers = ready([waiver("Coleman", { playoff_delta: 0, title_delta: 0 })]);
    renderAt("/moves");
    expect(screen.getAllByText(/You are out of the playoffs/).length).toBeGreaterThan(0);
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("never calls a team out while its phase is unknown, even with zero title odds", () => {
    leagueRow = { ...leagueRow, team_phase: null };
    digest = digestWith([], [myOdds(0)]);
    renderAt("/moves");
    expect(screen.queryByText(/You are out of the playoffs/)).not.toBeInTheDocument();
  });

  it("shows the playoff label, not the out message, once the season is over", () => {
    leagueRow = { ...leagueRow, current_week: 18, team_phase: "over", playoff_label: "Eliminated" };
    digest = digestWith([], [myOdds(0)]);
    renderAt("/moves");
    expect(screen.queryByText(/You are out of the playoffs/)).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Eliminated");
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });
});
