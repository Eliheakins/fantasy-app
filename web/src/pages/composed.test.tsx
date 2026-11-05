import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import Players from "./Players";
import Season from "./Season";
import ThisWeek from "./ThisWeek";

vi.mock("@/lib/league", () => ({
  useLeague: () => ({ league: "a", leagues: { kind: "ready", data: [{ league_key: "a", name: "L", current_week: 9 }] } }),
}));
vi.mock("@/features/digest/DigestView", async () => ({ DigestView: (await import("@/test/stubPage")).stubSection("digest") }));
vi.mock("@/features/home/HomeLeagues", async () => ({ HomeLeagues: (await import("@/test/stubPage")).stubSection("leagues") }));
vi.mock("@/features/thisweek/ThisWeekBoard", async () => ({ ThisWeekBoard: (await import("@/test/stubPage")).stubSection("board") }));
vi.mock("@/features/thisweek/Answer", () => ({ Answer: () => <span>answer</span> }));
vi.mock("@/features/outlook/OutlookView", async () => ({ OutlookView: (await import("@/test/stubPage")).stubSection("outlook") }));
vi.mock("@/features/league/LeagueView", async () => ({ LeagueView: (await import("@/test/stubPage")).stubSection("league") }));
vi.mock("@/features/players/PlayersView", async () => ({ PlayersView: (await import("@/test/stubPage")).stubSection("players") }));
vi.mock("@/pages/Scoreboard", () => ({ default: () => <p>scores</p> }));

describe("composed pages", () => {
  it.each([
    ["What should I do this week?", ThisWeek],
    ["Season", Season],
    ["Players", Players],
  ])("%s has exactly one h1", (title, Page) => {
    render(<MemoryRouter><Page /></MemoryRouter>);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("heading", { level: 1, name: title })).toBeInTheDocument();
  });

  it("the eyebrow shows the current week on pages that ignore ?week= and the selected week on Season", () => {
    const { unmount } = render(<MemoryRouter initialEntries={["/?week=4"]}><ThisWeek /></MemoryRouter>);
    expect(screen.getByText("This week · Week 9 · L")).toBeInTheDocument();
    unmount();
    render(<MemoryRouter initialEntries={["/season?week=4"]}><Season /></MemoryRouter>);
    expect(screen.getByText("Season · Week 4 · L")).toBeInTheDocument();
  });
});
