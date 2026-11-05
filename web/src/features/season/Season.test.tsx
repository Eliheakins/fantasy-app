import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ApiState } from "@/api/envelope";
import { RootForSection } from "./RootFor";
import { SeasonHeader } from "./SeasonHeader";
import { SeasonOdds } from "./SeasonOdds";
import { WhatYouNeed } from "./WhatYouNeed";

let responder: (path: string) => ApiState<unknown>;
vi.mock("@/lib/league", () => ({ useLeagueApi: (path: string) => responder(path) }));

const ready = (data: unknown): ApiState<unknown> => ({ kind: "ready", data });
const odds = [
  { roster_id: 1, team_name: "Lisan", p_playoffs: 0.68, p_bye: 0.18, p_title: 0.1, exp_wins: 7, is_me: true },
  { roster_id: 2, team_name: "Rival", p_playoffs: 0.4, p_bye: 0.1, p_title: 0.05, exp_wins: 7, is_me: false },
];
const run = (run_at: string, mine: number) => [
  { run_at, roster_id: 1, team_name: "Lisan", p_playoffs: mine, p_title: 0.1 },
  { run_at, roster_id: 2, team_name: "Rival", p_playoffs: 0.4, p_title: 0.1 },
];
const need = [0, 1, 2, 3].map((wins) => ({ n_games: 4, wins, n_runs: 5000, p_condition: 0.25, p_playoffs: 0.3 + 0.2 * wins }));
const o = (winner: number, loser: number, d: number) => ({
  winner_id: winner, loser_id: loser, winner: `Team ${winner}`, loser: `Team ${loser}`, involves_me: false,
  p_condition: 0.5, n_runs: 9000, d_playoffs: d, d_title: 0,
});
const events = [
  { kind: "trade", when: "2026-10-25T12:00:00+00:00", run_at: "2026-10-27T06:00:00+00:00", label: "Trade: got Ray Runner; sent nobody" },
  { kind: "injury", when: "2026-10-01T12:00:00+00:00", run_at: null, label: "Quinn Back listed Out" },
];

const by = (table: Record<string, unknown>) => (p: string) => ready(table[p] ?? []);
const view = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe("Season header", () => {
  it("answers with the odds and the change since the last week's run", () => {
    responder = by({ "season-odds": odds, digest: { odds_change: [{ is_me: true, d_playoffs: 0.05 }] } });
    view(<SeasonHeader eyebrow="Season" />);
    expect(screen.getByRole("heading", { level: 1, name: "68% to make the playoffs" })).toBeInTheDocument();
    expect(screen.getByText(/\+5\.0/)).toBeInTheDocument();
    expect(screen.getByText(/A bye is 18% and the title 10%/)).toBeInTheDocument();
  });
  it("keeps a question as the h1 until the odds load", () => {
    responder = () => ({ kind: "loading" });
    view(<SeasonHeader eyebrow="Season" />);
    expect(screen.getByRole("heading", { level: 1, name: "Am I making the playoffs?" })).toBeInTheDocument();
  });
});

describe("What you need", () => {
  it("shows odds by wins and the wins that reach good odds", () => {
    responder = by({ "win-needs": need });
    view(<WhatYouNeed />);
    expect(screen.getByText("Win 3 of your next 4 and you are at 90% to make the playoffs.")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Win 2 of 4: 70% to make the playoffs" })).toBeInTheDocument();
    expect(screen.getByText(/Win 4 of 4/)).toBeInTheDocument();
    expect(screen.getByText(/never happened/)).toBeInTheDocument();
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
    expect(screen.getByText(/Trade: got Ray Runner/)).toBeInTheDocument();
    expect(screen.getByText("(before the first saved run)")).toBeInTheDocument();
  });
  it("waits for a second run before drawing", () => {
    responder = by({ "season-odds": odds, "odds-history": run("2026-10-20T06:00:00+00:00", 0.6) });
    view(<SeasonOdds />);
    expect(screen.queryByRole("heading", { name: "Playoff odds over the season" })).toBeNull();
  });
});
