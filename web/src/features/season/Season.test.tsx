import { render, screen, within } from "@testing-library/react";
import { leaguePath } from "@/test/fakeApi";
import { MemoryRouter } from "react-router";
import type { ApiState } from "@/api/envelope";
import { HISTORY_WAIT_MESSAGE } from "@/features/season/outlook/logic";
import { RootForSection } from "./RootFor";
import { SeasonHeader } from "./SeasonHeader";
import { SeasonOdds } from "./SeasonOdds";
import { WhatYouNeed } from "./WhatYouNeed";

let responder: (path: string) => ApiState<unknown>;
let leagueRow: { current_week: number; playoff_week_start: number } | undefined;
beforeEach(() => {
  leagueRow = undefined;
});
vi.mock("@/lib/league", () => ({
  useLeagueApi: (route: string, query?: object) => responder(leaguePath(route, query)),
  useLeague: () => ({ league: "a" }),
  useLeagueRow: () => leagueRow,
}));

const ready = (data: unknown): ApiState<unknown> => ({ kind: "ready", data });
const odds = [
  { roster_id: 1, team_name: "Lisan", p_playoffs: 0.68, p_bye: 0.18, p_title: 0.1, exp_wins: 7, is_me: true },
  { roster_id: 2, team_name: "Rival", p_playoffs: 0.4, p_bye: 0.1, p_title: 0.05, exp_wins: 7, is_me: false },
];
const weekOf = (run_at: string) => (run_at < "2026-10-27" ? 7 : 8);
const run = (run_at: string, mine: number) => [
  { run_at, roster_id: 1, team_name: "Lisan", p_playoffs: mine, p_title: 0.1, as_of_week: weekOf(run_at) },
  { run_at, roster_id: 2, team_name: "Rival", p_playoffs: 0.4, p_title: 0.1, as_of_week: weekOf(run_at) },
];
const need = [0, 1, 2, 3].map((wins) => ({ n_games: 4, wins, n_runs: 5000, p_condition: 0.25, p_playoffs: 0.3 + 0.2 * wins }));
const o = (winner: number, loser: number, d: number) => ({
  winner_id: winner,
  loser_id: loser,
  winner: `Team ${winner}`,
  loser: `Team ${loser}`,
  involves_me: false,
  p_condition: 0.5,
  n_runs: 9000,
  d_playoffs: d,
  d_title: 0,
});
const events = [
  { kind: "trade", when: "2026-10-25T12:00:00+00:00", run_at: "2026-10-27T06:00:00+00:00", label: "Trade: got Ray Runner; sent nobody" },
  { kind: "injury", when: "2026-10-01T12:00:00+00:00", run_at: null, label: "Quinn Back listed Out" },
];

const noBracket: ApiState<unknown> = { kind: "no_data", message: "x" };
/** Answers only the listed routes: `data` as ready, `states` as given; any other route fails the test. */
const by =
  (data: Record<string, unknown>, states: Record<string, ApiState<unknown>> = {}) =>
  (p: string): ApiState<unknown> => {
    if (p in states) return states[p]!;
    if (p in data) return ready(data[p]);
    throw new Error(`unlisted route: ${p}`);
  };
const view = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("Season header", () => {
  it("answers with the odds and the change since the last week's run", () => {
    responder = by({ "season-odds": odds, digest: { odds_change: [{ is_me: true, d_playoffs: 0.05 }] } });
    view(<SeasonHeader eyebrow="Season" />);
    expect(screen.getByRole("heading", { level: 1, name: "68% to make the playoffs" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "68%" })).toHaveAccessibleDescription(/what drives this/);
    expect(screen.getByText(/\+5\.0/)).toBeInTheDocument();
    expect(screen.getByText(/pp since the last week/)).toBeInTheDocument();
    expect(screen.getByText(/A bye is/).textContent).toMatch(/A bye is 18%, what drives this and the title 10%, what drives this\./);
    expect(screen.getByRole("button", { name: /\+5\.0.*what drives this/ })).toBeInTheDocument();
  });
  it("keeps a stable h1 until the odds load", () => {
    responder = by({}, { "season-odds": { kind: "loading" }, digest: { kind: "loading" } });
    view(<SeasonHeader eyebrow="Season" />);
    expect(screen.getByRole("heading", { level: 1, name: "Season" })).toBeInTheDocument();
  });
});

describe("What you need", () => {
  it("shows odds by wins and the wins that reach good odds", () => {
    responder = by({ "win-needs": need });
    view(<WhatYouNeed />);
    expect(screen.getByText("Win 3 of your next 4 and you are at 90% to make the playoffs.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /70%.*what drives this/ })).toBeInTheDocument();
    expect(screen.getByText(/Win 4 of 4/)).toBeInTheDocument();
    expect(screen.getByText(/never happened/)).toBeInTheDocument();
  });
  it("says so when every win count has too few seasons behind it", () => {
    responder = by({ "win-needs": need.map((n) => ({ ...n, n_runs: 999 })) });
    view(<WhatYouNeed />);
    expect(screen.getByText(/Too few simulated seasons/)).toBeInTheDocument();
  });
  it("shows an error from the API", () => {
    responder = by({}, { "win-needs": { kind: "error", error: { message: "boom", code: null } } });
    view(<WhatYouNeed />);
    expect(screen.getByText(/boom/)).toBeInTheDocument();
  });
  it("points at make refresh when the table has not been written", () => {
    responder = by({ "win-needs": [] });
    view(<WhatYouNeed />);
    expect(screen.getByText(/run make refresh to see this/)).toBeInTheDocument();
  });
});

describe("Who to root for", () => {
  it("lists the side to back in each other game, biggest swing first", () => {
    responder = by({ "what-if?week=0": [o(3, 4, 0.01), o(4, 3, -0.01), o(5, 6, -0.07), o(6, 5, 0.05)] });
    view(<RootForSection />);
    const items = within(screen.getByRole("list")).getAllByRole("listitem");
    expect(items[0]).toHaveTextContent("Root for Team 6 over Team 5");
    expect(items[1]).toHaveTextContent("Root for Team 3 over Team 4");
    expect(within(items[0]!).getByRole("button", { name: /12.*what drives this/ })).toBeInTheDocument();
  });
});

describe("Who to root for, other states", () => {
  it("says no game moves the odds when nothing is usable", () => {
    responder = by({ "what-if?week=0": [] });
    view(<RootForSection />);
    expect(screen.getByText(/No other game this week moves your odds/)).toBeInTheDocument();
  });
  it("shows an error from the API", () => {
    responder = by({}, { "what-if?week=0": { kind: "error", error: { message: "boom", code: null } } });
    view(<RootForSection />);
    expect(screen.getByText(/boom/)).toBeInTheDocument();
  });
  it("says how many simulated seasons are behind a row", () => {
    responder = by({ "what-if?week=0": [o(5, 6, -0.07), o(6, 5, 0.05)] });
    view(<RootForSection />);
    expect(screen.getByText(/from 9,000 simulated seasons/)).toBeInTheDocument();
  });
});

describe("Season odds chart", () => {
  it("lists the marked events and says which sit before the first run", () => {
    responder = by({
      "season-odds": odds,
      "odds-history": [...run("2026-10-20T06:00:00+00:00", 0.6), ...run("2026-10-27T06:00:00+00:00", 0.7)],
      "season-events": events,
    });
    view(<SeasonOdds />);
    expect(screen.getByRole("heading", { name: "Playoff odds over the season" })).toBeInTheDocument();
    expect(screen.getByText(/Trade: got Ray Runner/).textContent).not.toMatch(/Trade: Trade/);
    expect(screen.getByText(/before the first saved run, so not drawn/)).toBeInTheDocument();
    expect(screen.getByText(/week 8, your odds 70%/)).toBeInTheDocument();
  });
  it("labels the events list and points the chart at it", () => {
    responder = by({
      "season-odds": odds,
      "odds-history": [...run("2026-10-20T06:00:00+00:00", 0.6), ...run("2026-10-27T06:00:00+00:00", 0.7)],
      "season-events": events,
    });
    view(<SeasonOdds />);
    const heading = screen.getByRole("heading", { name: "Marked events" });
    expect(screen.getByRole("img", { name: /Playoff odds by week/ })).toHaveAttribute("aria-describedby", heading.id);
    expect(screen.getByRole("table", { name: /Playoff odds by week/ })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Marked events" })).toBeInTheDocument();
  });
  it("plots title odds from the first playoff week and playoff odds before it, without asking for the bracket", () => {
    leagueRow = { current_week: 8, playoff_week_start: 8 };
    const asked: string[] = [];
    responder = (p) => {
      asked.push(p);
      return by({
        "season-odds": odds,
        "odds-history": [...run("2026-10-20T06:00:00+00:00", 0.6), ...run("2026-10-27T06:00:00+00:00", 0.97)],
        "season-events": [],
      })(p);
    };
    view(<SeasonOdds />);
    expect(asked).not.toContain("bracket");
    const table = screen.getByRole("table", { name: /title odds from week 8/ });
    const cells = (week: string) => within(within(table).getByRole("row", { name: new RegExp(`^Wk ${week}`) })).getAllByRole("cell");
    expect(cells("7")[1]).toHaveTextContent("60%");
    expect(cells("8")[1]).toHaveTextContent("10%");
  });
  it("says the marks are unavailable on an events error, not that there is nothing to mark", () => {
    responder = by(
      {
        "season-odds": odds,
        "odds-history": [...run("2026-10-20T06:00:00+00:00", 0.6), ...run("2026-10-27T06:00:00+00:00", 0.7)],
      },
      { "season-events": { kind: "error", error: { message: "boom", code: null } } },
    );
    view(<SeasonOdds />);
    expect(screen.getByText(/Marks unavailable: boom/)).toBeInTheDocument();
    expect(screen.queryByText(/Nothing to mark yet/)).toBeNull();
  });
  it("keeps the section and shows loading or errors for odds and history", () => {
    responder = by({ "odds-history": [], "season-events": [] }, { "season-odds": { kind: "loading" }, bracket: noBracket });
    const { unmount } = view(<SeasonOdds />);
    expect(screen.getByRole("heading", { name: "Playoff odds over the season" })).toBeInTheDocument();
    expect(screen.getByText(/Loading/)).toBeInTheDocument();
    unmount();
    responder = by(
      { "season-odds": odds, "season-events": [] },
      { "odds-history": { kind: "error", error: { message: "boom", code: null } }, bracket: noBracket },
    );
    view(<SeasonOdds />);
    expect(screen.getByText(/boom/)).toBeInTheDocument();
  });
  it("waits for a second run before drawing", () => {
    responder = by({ "season-odds": odds, "odds-history": run("2026-10-20T06:00:00+00:00", 0.6), "season-events": [] });
    view(<SeasonOdds />);
    expect(screen.queryByRole("heading", { name: "Marked events" })).toBeNull();
    expect(screen.getByText(HISTORY_WAIT_MESSAGE)).toBeInTheDocument();
  });
});
