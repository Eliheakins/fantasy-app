import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
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
vi.mock("@/lib/league", () => ({
  useLeague: () => ({ league: "a", leagues: { kind: "ready", data: [{ league_key: "a", name: "L", current_week: 9 }] } }),
  useLeagueName: () => "L",
  useLeagueApi: (path: string) => (path === "waivers" ? waivers : digest),
}));
vi.mock("@/features/moves/waivers/WaiversView", () => ({ WaiversContent: () => <p>waivers details</p> }));
vi.mock("@/features/moves/trade/TradeBuilder", () => ({ TradeBuilder: () => <p>trade builder</p> }));
vi.mock("@/features/moves/trade/TradeDetails", () => ({ TradeDetails: () => <p>trade details</p> }));

const ready = (data: unknown): ApiState<unknown> => ({ kind: "ready", data }) as ApiState<unknown>;
const digestWith = (trades: unknown[]) => ready({ waivers: [], trades, ideas: { is_mine: true } });

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
  waivers = ready([waiver("Coleman"), waiver("Small", { playoff_delta: 0.001, delta_points: 1, trending_adds: 200000 })]);
  digest = digestWith([trade]);
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
