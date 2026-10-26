import { render, screen } from "@testing-library/react";
import type { ApiState } from "@/api/envelope";
import Digest from "@/pages/Digest";
import type { DigestData } from "./types";

let responder: (path: string) => ApiState<unknown>;
vi.mock("@/lib/league", () => ({
  useLeagueApi: (path: string) => responder(path),
  useLeague: () => ({ league: "t", leagues: { kind: "ready", data: [] } }),
}));

const ready = (data: unknown): ApiState<unknown> => ({ kind: "ready", data });

const ideas = { is_mine: true, created_at: "2026-10-25T08:00:00+00:00", as_of_week: 7, current_week: 7, trade_deadline: 11, deadline_passed: false };
const waiver = { kind: "waiver", partner: null, give: "DJ Moore", get: "Malik Willis", give_ids: [], get_ids: ["g"], rank: 1, playoff_delta: 0.0159, title_delta: 0.0049, se_title: 0.001, delta_points: 8.2 };
const trade = { ...waiver, kind: "trade", partner: "The Pinheads", give: "A (RB)", get: "B (WR)", delta_points: null };
const odds = (over: object = {}) => ({
  roster_id: 1, team_name: "Lisan", is_me: true, as_of_week: 7, prev_as_of_week: null, p_playoffs: 0.86, p_title: 0.24, d_playoffs: null, d_title: null, ...over,
});
const base: DigestData = {
  last_week: { week: 6, roster_id: 1, team_name: "Lisan", opponent: "Eggplant", points: 137.8, opp_points: 76.4, result: "W", bench_points_left: 33.3, luck: 0.22 },
  performance: [
    { gsis_id: "a", full_name: "Cook", position: "RB", points: 24.3, projection: 15, diff: 9.3 },
    { gsis_id: "b", full_name: "Darnold", position: "QB", points: 13, projection: null, diff: null },
  ],
  odds_change: [odds()],
  waivers: [waiver],
  trades: [trade],
  ideas,
} as DigestData;

function respond(digest: ApiState<unknown>, actions: ApiState<unknown> = ready([])) {
  responder = (p) => (p === "digest" ? digest : actions);
}

describe("Digest page", () => {
  it("shows the result, the signed projection miss, a null projection and 'no earlier run'", () => {
    respond(ready(base));
    render(<Digest />);
    expect(screen.getByRole("heading", { level: 1, name: "Weekly digest" })).toBeInTheDocument();
    expect(screen.getByText(/Week 6: Won 137.8 to 76.4 against Eggplant/)).toBeInTheDocument();
    expect(screen.getByText("+9.3 ▲")).toBeInTheDocument();
    expect(screen.getAllByText("no projection").length).toBeGreaterThan(0);
    expect(screen.getAllByText("no earlier run").length).toBe(2);
    expect(screen.getByText("Malik Willis")).toBeInTheDocument();
    expect(screen.getByText("The Pinheads")).toBeInTheDocument();
    expect(screen.getByText(/As of .*\(.* ago\), week 7 refresh/)).toBeInTheDocument();
  });

  it("shows signed odds changes when an earlier run exists", () => {
    respond(ready({ ...base, odds_change: [odds({ prev_as_of_week: 6, d_playoffs: 0.05, d_title: -0.02 })] }));
    render(<Digest />);
    expect(screen.getByText("+5.0 ▲")).toBeInTheDocument();
    expect(screen.getByText("-2.0 ▼")).toBeInTheDocument();
    expect(screen.getByText(/against the last run of week 6/)).toBeInTheDocument();
  });

  it("week 1 has no prior week", () => {
    respond(ready({ ...base, last_week: null, performance: [], odds_change: [], ideas: { ...ideas, current_week: 1, as_of_week: 1 } }));
    render(<Digest />);
    expect(screen.getByText(/Week 1: there is no earlier week yet/)).toBeInTheDocument();
    expect(screen.getByText(/No starters were scored last week/)).toBeInTheDocument();
  });

  it("after the deadline the trade list says so and waivers still show", () => {
    respond(ready({ ...base, trades: [], ideas: { ...ideas, deadline_passed: true, current_week: 12, as_of_week: 12 } }));
    render(<Digest />);
    expect(screen.getByText(/deadline \(week 11\) has passed/)).toBeInTheDocument();
    expect(screen.getByText("Malik Willis")).toBeInTheDocument();
  });

  it("another team's view explains that ideas are for my team only, with no wrong rows", () => {
    respond(ready({ ...base, waivers: [], trades: [], ideas: { ...ideas, is_mine: false } }));
    render(<Digest />);
    expect(screen.getAllByText(/only for the team that is yours/).length).toBe(2);
    expect(screen.queryByText("Malik Willis")).toBeNull();
  });

  it("flags ideas from an earlier week and a digest that never ran", () => {
    respond(ready({ ...base, ideas: { ...ideas, current_week: 8 } }));
    const { unmount } = render(<Digest />);
    expect(screen.getAllByText(/from week 7; it is now week 8/).length).toBe(2);
    unmount();
    respond(ready({ ...base, waivers: [], trades: [], ideas: { ...ideas, created_at: null, as_of_week: null } }));
    render(<Digest />);
    expect(screen.getAllByText(/Run make refresh/).length).toBeGreaterThan(0);
  });

  it("shows the next lineup action, skipping the waiver one", () => {
    const actions = [
      { kind: "Waiver", text: "Add X, drop Y: +1.0% playoff odds, +2.0 points", delta_points: 2, share_better: null },
      { kind: "Lineup", text: "Start A over B (+3.0 points)", delta_points: 3, share_better: null },
    ];
    respond(ready(base), ready(actions));
    render(<Digest />);
    expect(screen.getByText("Start A over B")).toBeInTheDocument();
    expect(screen.queryByText(/Add X/)).toBeNull();
  });

  it("loading, running, no_data and error", () => {
    const cases: [ApiState<unknown>, RegExp][] = [
      [{ kind: "loading" }, /Loading/],
      [{ kind: "running", startedAt: null }, /Working/],
      [{ kind: "no_data", message: "No league yet." }, /No league yet/],
      [{ kind: "error", error: { message: "boom", code: null } }, /boom/],
    ];
    for (const [state, text] of cases) {
      respond(state, state);
      const { unmount } = render(<Digest />);
      expect(screen.getAllByText(text).length).toBeGreaterThan(0);
      unmount();
    }
  });
});
