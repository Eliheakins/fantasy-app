import { render, screen, within } from "@testing-library/react";
import { leaguePath } from "@/test/fakeApi";
import userEvent from "@testing-library/user-event";
import type { ApiState } from "@/api/envelope";
import { LeagueView as League } from "./LeagueView";

let responder: (path: string) => ApiState<unknown>;
vi.mock("@/lib/league", () => ({
  useLeagueApi: (route: string, query?: object) => responder(leaguePath(route, query)),
  useLeague: () => ({ league: "t", leagues: { kind: "ready", data: [{ league_key: "t", current_week: 7 }] } }),
}));

const ready = (data: unknown): ApiState<unknown> => ({ kind: "ready", data });
const team = (roster_id: number, team_name: string, is_me = false) => ({ roster_id, team_name, is_me });
const power = [
  {
    ...team(1, "Lisan", true),
    rank: 2,
    exp_points_week: 140,
    exp_wins: 7.7,
    p_playoffs: 0.76,
    p_title: 0.08,
    sos_remaining: 139,
    sos_rank: 1,
  },
  { ...team(2, "Rival"), rank: 1, exp_points_week: 150, exp_wins: 7.5, p_playoffs: 0.5, p_title: 0.1, sos_remaining: 130, sos_rank: 2 },
];
const luck = [
  { ...team(1, "Lisan", true), weeks: 6, wins: 4, losses: 2, ties: 0, ap_wins: 32, ap_losses: 22, ap_ties: 0, exp_wins: 3.56, luck: 0.44 },
  { ...team(2, "Rival"), weeks: 6, wins: 2, losses: 4, ties: 0, ap_wins: 34, ap_losses: 20, ap_ties: 0, exp_wins: 3.78, luck: -1.78 },
];
const grades = [
  { ...team(1, "Lisan", true), weeks: 6, actual_points: 854.7, optimal_points: 990.9, efficiency: 0.8625, bench_points_left: 136.2 },
];
const teamGrades = ["overall", "QB"].flatMap((position) => [
  { ...team(1, "Lisan", true), position, vor_per_week: 8, depth_per_week: 0.4, score: 1, rank: 1, grade: "A" },
  { ...team(2, "Rival"), position, vor_per_week: 4, depth_per_week: 0.1, score: -1, rank: 2, grade: "C" },
]);
const outcome = (winner: string, loser: string, o: object = {}) => ({
  winner_id: 1,
  loser_id: 2,
  winner,
  loser,
  involves_me: true,
  p_condition: 0.5,
  n_runs: 10000,
  d_playoffs: 0.119,
  d_title: -0.0142,
  ...o,
});
const whatIf = [outcome("Lisan", "Rival"), outcome("Rival", "Lisan", { n_runs: 400 })];

function respond(over: Partial<Record<string, ApiState<unknown>>> = {}) {
  responder = (p) =>
    over[p] ??
    (p === "power-rankings"
      ? ready(power)
      : p === "luck"
        ? ready(luck)
        : p === "manager-grades"
          ? ready(grades)
          : p === "team-grades"
            ? ready(teamGrades)
            : ready(whatIf));
}

describe("League page", () => {
  it("ready: ranks teams, marks mine in text, shows signed luck and efficiency", async () => {
    respond();
    render(<League />);
    expect(screen.getByRole("list", { name: /Power rankings/ })).toBeInTheDocument();
    expect(screen.getAllByText("Lisan (you)").length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("tab", { name: "Luck and all-play" }));
    expect(screen.getByText("+0.44 ▲")).toBeInTheDocument();
    expect(screen.getByText("-1.78 ▼")).toBeInTheDocument();
    expect(screen.getByText("4-2")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Lineup efficiency" }));
    expect(screen.getByText("86%")).toBeInTheDocument();
  });
  it("puts the league tables under one League details section with tabs, power rankings first", async () => {
    respond();
    render(<League />);
    expect(screen.getByRole("heading", { level: 2, name: "League details" })).toBeInTheDocument();
    const tabs = screen.getAllByRole("tab").map((t) => t.textContent);
    expect(tabs).toEqual([
      "Power rankings",
      "Schedule strength",
      "Positional strength",
      "Luck and all-play",
      "Lineup efficiency",
      "What if",
    ]);
    expect(screen.getByRole("tab", { name: "Power rankings" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("table", { name: "Positional strength by team" })).toBeNull();
    await userEvent.click(screen.getByRole("tab", { name: "Positional strength" }));
    expect(screen.getByRole("table", { name: "Positional strength by team" })).toBeInTheDocument();
  });
  it("shows the positional strength grid with its measure and weighting", async () => {
    respond();
    render(<League />);
    await userEvent.click(screen.getByRole("tab", { name: "Positional strength" }));
    expect(screen.getByRole("table", { name: "Positional strength by team" })).toBeInTheDocument();
    const section = screen.getByRole("region", { name: "Positional strength" });
    await userEvent.click(within(section).getByRole("button", { name: "How this is calculated" }));
    expect(screen.getByText(/above a free-agent stand-in.*75% starters, 25% bench depth/)).toBeInTheDocument();
  });
  it("what-if shows deltas for a well-sampled outcome and hides a thin one with a note", async () => {
    respond();
    render(<League />);
    await userEvent.click(screen.getByRole("tab", { name: "What if" }));
    expect(screen.getByText("+11.9 ▲")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("radio", { name: "Rival wins" }));
    expect(screen.queryByText("+11.9 ▲")).toBeNull();
    expect(screen.getByText(/only 400 of the simulated seasons/)).toBeInTheDocument();
  });
  it("what-if with no matchups says so", async () => {
    respond({ "what-if?week=7": ready([]) });
    render(<League />);
    await userEvent.click(screen.getByRole("tab", { name: "What if" }));
    expect(screen.getByText(/No matchups to test/)).toBeInTheDocument();
  });
  it("loading, running, no_data and error", () => {
    const cases: [ApiState<unknown>, RegExp][] = [
      [{ kind: "loading" }, /Loading/],
      [{ kind: "running", startedAt: null }, /Working/],
      [{ kind: "no_data", message: "No league yet." }, /No league yet/],
      [{ kind: "error", error: { message: "boom", code: null } }, /boom/],
    ];
    for (const [state, text] of cases) {
      responder = () => state;
      const { unmount } = render(<League />);
      expect(screen.getAllByText(text).length).toBeGreaterThan(0);
      unmount();
    }
  });
  it("empty power rankings say so and leave the other sections", async () => {
    respond({ "power-rankings": ready([]) });
    render(<League />);
    expect(screen.getByText("Nothing to show yet.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Schedule strength" }));
    expect(screen.getByText("Nothing to show yet.")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Luck and all-play" })).toBeInTheDocument();
  });
  it("a failing section reports its own error and leaves the rest", async () => {
    respond({ luck: { kind: "error", error: { message: "luck broke", code: null } } });
    render(<League />);
    expect(screen.getByRole("list", { name: /Power rankings/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Luck and all-play" }));
    expect(screen.getByText(/luck broke/)).toBeInTheDocument();
  });
});
