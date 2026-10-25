import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ApiState } from "@/api/envelope";
import Outlook from "@/pages/Outlook";
import Players from "@/pages/Players";
import { HISTORY_WAIT_MESSAGE } from "./logic";

let responder: (path: string) => ApiState<unknown>;
const paths: string[] = [];
vi.mock("@/lib/league", () => ({
  useLeagueApi: (path: string) => {
    paths.push(path);
    return responder(path);
  },
}));

const ready = (data: unknown): ApiState<unknown> => ({ kind: "ready", data });
const odds = [
  { roster_id: 1, team_name: "Lisan", p_playoffs: 0.71, p_bye: 0.2, p_title: 0.14, exp_wins: 8.46, is_me: true },
  { roster_id: 2, team_name: "Rival", p_playoffs: 0.4, p_bye: 0.1, p_title: 0.05, exp_wins: 7, is_me: false },
];
const run = (run_at: string) => [
  { run_at, roster_id: 1, team_name: "Lisan", p_playoffs: 0.7, p_title: 0.1 },
  { run_at, roster_id: 2, team_name: "Rival", p_playoffs: 0.4, p_title: 0.1 },
];
const players = [
  { gsis_id: "g1", full_name: "Ann Back", position: "RB", owner: "Lisan", recent_ppg: 10, expected_ppg: 11, next_ppg: 12.5, change: 2.5, chance_to_play: 0.85, label: "Improving", why: "Teammate out" },
];

function outlookWith(history: unknown) {
  responder = (p) =>
    p === "season-odds" ? ready(odds)
    : p === "seeds" ? ready([{ seed: 1, p: 0.3 }])
    : p === "schedule" ? ready([{ week: 9, opponent: "Rival", my_points: 100, their_points: 95, win_chance: 0.6 }])
    : ready(history);
}

describe("Outlook page", () => {
  it("ready: marks my team in text, shows seeds and schedule, waits for a second run", () => {
    outlookWith(run("2026-10-01T00:00"));
    render(<Outlook />);
    expect(screen.getByText("Lisan (you)")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Where you finish" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Your remaining schedule" })).toBeInTheDocument();
    expect(screen.getByText(HISTORY_WAIT_MESSAGE)).toBeInTheDocument();
  });
  it("ready: shows the history chart with its table from two runs", () => {
    outlookWith([...run("2026-10-01T00:00"), ...run("2026-10-08T00:00")]);
    render(<Outlook />);
    expect(screen.getByRole("heading", { name: "Season odds, all teams" })).toBeInTheDocument();
    expect(screen.queryByText(HISTORY_WAIT_MESSAGE)).toBeNull();
  });
  it("loading, running, no_data and error", () => {
    const cases: [ApiState<unknown>, RegExp][] = [
      [{ kind: "loading" }, /Loading/],
      [{ kind: "running", startedAt: null }, /Working/],
      [{ kind: "no_data", message: "No outlook yet." }, /No outlook yet/],
      [{ kind: "error", error: { message: "boom", code: null } }, /boom/],
    ];
    for (const [state, text] of cases) {
      responder = () => state;
      const { unmount } = render(<Outlook />);
      expect(screen.getAllByText(text).length).toBeGreaterThan(0);
      unmount();
    }
  });
  it("empty odds shows the no-data copy", () => {
    responder = () => ready([]);
    render(<Outlook />);
    expect(screen.getByText(/make refresh/)).toBeInTheDocument();
  });
});

describe("Players page", () => {
  it("ready: renders the row and switches scope", async () => {
    responder = () => ready(players);
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
      [ready([]), /No players to show/],
      [{ kind: "loading" }, /Loading/],
      [{ kind: "running", startedAt: null }, /Working/],
      [{ kind: "no_data", message: "No outlook yet." }, /No outlook yet/],
      [{ kind: "error", error: { message: "boom", code: null } }, /boom/],
    ];
    for (const [state, text] of cases) {
      responder = () => state;
      const { unmount } = render(<Players />);
      expect(screen.getByText(text)).toBeInTheDocument();
      unmount();
    }
  });
});
