import { type RenderResult, render as rtlRender, screen } from "@testing-library/react";
import { leaguePath, onlyRoutes } from "@/test/fakeApi";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import userEvent from "@testing-library/user-event";
import type { ApiState } from "@/api/envelope";
import { OutlookView as Outlook } from "./OutlookView";
import { PlayersView as Players } from "@/features/players/PlayersView";

/** Player names link to Explore, which needs a router. */
const render = (ui: ReactElement): RenderResult => rtlRender(<MemoryRouter>{ui}</MemoryRouter>);

let responder: (path: string) => ApiState<unknown>;
let paths: string[] = [];
beforeEach(() => {
  paths = [];
});
vi.mock("@/lib/league", () => ({
  useLeagueApi: (route: string, query?: object) => {
    const path = leaguePath(route, query);
    paths.push(path);
    return responder(path);
  },
  usePlayoffTeams: () => 6,
}));

const ready = (data: unknown): ApiState<unknown> => ({ kind: "ready", data });
const odds = [
  { roster_id: 1, team_name: "Lisan", p_playoffs: 0.71, p_bye: 0.2, p_title: 0.14, exp_wins: 8.46, is_me: true },
  { roster_id: 2, team_name: "Rival", p_playoffs: 0.4, p_bye: 0.1, p_title: 0.05, exp_wins: 7, is_me: false },
];
const players = [
  {
    gsis_id: "g1",
    full_name: "Ann Back",
    position: "RB",
    owner: "Lisan",
    recent_ppg: 10,
    expected_ppg: 11,
    next_ppg: 12.5,
    change: 2.5,
    chance_to_play: 0.85,
    label: "Improving",
    why: "Teammate out",
  },
];

/** The Outlook's four routes, all in one state. */
const outlook = (state: ApiState<unknown>) => onlyRoutes({ bracket: state, "season-odds": state, seeds: state, schedule: state });

describe("Outlook page", () => {
  it("ready: marks my team in text, shows seeds and schedule, and leaves the odds chart to Season", () => {
    responder = onlyRoutes({
      bracket: { kind: "no_data", message: "x" },
      "season-odds": ready(odds),
      seeds: ready([{ seed: 1, p: 0.3 }]),
      schedule: ready([{ week: 9, opponent: "Rival", my_points: 100, their_points: 95, win_chance: 0.6 }]),
    });
    render(<Outlook />);
    expect(screen.getByText("Lisan (you)")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Where you finish" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Your remaining schedule" })).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Chance of each seed" })).toBeInTheDocument();
    expect(paths).not.toContain("odds-history");
  });
  it("loading, running, no_data and error", () => {
    const cases: [ApiState<unknown>, RegExp][] = [
      [{ kind: "loading" }, /Loading/],
      [{ kind: "running", startedAt: null }, /Working/],
      [{ kind: "no_data", message: "No outlook yet." }, /No outlook yet/],
      [{ kind: "error", error: { message: "boom", code: null } }, /boom/],
    ];
    for (const [state, text] of cases) {
      responder = outlook(state);
      const { unmount } = render(<Outlook />);
      expect(screen.getAllByText(text).length).toBeGreaterThan(0);
      unmount();
    }
  });
  it("empty odds shows the no-data copy", () => {
    responder = outlook(ready([]));
    render(<Outlook />);
    expect(screen.getByText(/make refresh/)).toBeInTheDocument();
  });
});

describe("Players page", () => {
  it("ready: renders the row and switches scope", async () => {
    responder = onlyRoutes({ "outlook?scope=mine": ready(players), "outlook?scope=free": ready(players) });
    render(<Players />);
    expect(screen.getByText("Teammate out")).toBeInTheDocument();
    expect(screen.getByText("+2.5 ▲")).toBeInTheDocument();
    expect(screen.getByText("85%")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "Free agents" }));
    expect(paths).toContain("outlook?scope=free");
    expect(screen.getByRole("radio", { name: "Free agents" })).toBeChecked();
  });
  it("empty, loading, running, no_data, error", () => {
    const cases: [ApiState<unknown>, RegExp][] = [
      [ready([]), /No players in this group/],
      [{ kind: "loading" }, /Loading/],
      [{ kind: "running", startedAt: null }, /Working/],
      [{ kind: "no_data", message: "No outlook yet." }, /No outlook yet/],
      [{ kind: "error", error: { message: "boom", code: null } }, /boom/],
    ];
    for (const [state, text] of cases) {
      responder = onlyRoutes({ "outlook?scope=mine": state });
      const { unmount } = render(<Players />);
      expect(screen.getByText(text)).toBeInTheDocument();
      unmount();
    }
  });
});
