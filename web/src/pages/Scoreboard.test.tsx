import { render, screen, within } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { row } from "@/features/scoreboard/fixtures";
import { ScoreboardView } from "./Scoreboard";

describe("ScoreboardView", () => {
  test("says so when a week has no matchups", () => {
    render(<ScoreboardView rows={[]} week={16} asOf={null} />);
    expect(screen.getByText(/No matchups are set for week 16/)).toBeTruthy();
  });
  test("renders one labelled card per matchup with (you), status, ranges and a win split", () => {
    const rows = [
      row({ is_me: true, team_name: "Lisan" }, { team_name: "Bowers" }),
      row({ roster_id: 3, team_name: "Seals" }, { roster_id: 4, team_name: "tsd" }, { matchup_id: 2 }),
    ];
    render(<ScoreboardView rows={rows} week={7} asOf="Sun 1:00 PM" />);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    const mine = screen.getByRole("article", { name: "Lisan (you) versus Bowers" });
    expect(within(mine).getByText("Live")).toBeTruthy();
    expect(within(mine).getByText("Your matchup")).toBeTruthy();
    expect(mine.className).toContain("border-accent");
    expect(within(mine).getByRole("img", { name: "Chance to win: Lisan 60%, Bowers 40%" })).toBeTruthy();
    expect(within(mine).getAllByRole("img", { name: /^Median 110.0, range 90.0 to 130.0$/ })).toHaveLength(2);
    expect(screen.getByText(/Points as of Sun 1:00 PM/)).toBeTruthy();
  });
  test("a finished week shows final points, no win split and no freshness note", () => {
    const final = row({ win_prob: null, points: 101.2 }, { win_prob: null, points: 95 }, { status: "Final" });
    render(<ScoreboardView rows={[final]} week={3} asOf="Sun 1:00 PM" />);
    expect(screen.getByText("101.2")).toBeTruthy();
    expect(screen.queryByRole("img", { name: /Chance to win/ })).toBeNull();
    expect(screen.queryByText(/Points as of/)).toBeNull();
  });
});
