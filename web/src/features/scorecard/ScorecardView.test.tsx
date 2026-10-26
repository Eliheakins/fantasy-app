import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { ScorecardView } from "./ScorecardView";
import type { ScorecardData, ScorecardRow } from "./logic";

const excluded = { games: 50, scored: 40, not_final: 5, no_kickoff: 2, no_snapshot: 3, sleeper_missing: 0 };
const row = (o: Partial<ScorecardRow>): ScorecardRow => ({
  week: 7, position: "ALL", tier: -1, model: "learned", n: 40, mae: 5.2, rmse: 6, bias: -0.5, ...o,
});
const data = (rows: ScorecardRow[], weeks = [7]): ScorecardData => ({
  rows, excluded, weeks_archived: weeks, weeks_scored: weeks, has_quantiles: false, sleeper_first_fetch: null,
});

describe("ScorecardView", () => {
  test("empty state says when it fills and which weeks are archived", () => {
    render(<ScorecardView data={{ ...data([]), weeks_scored: [] }} />);
    expect(screen.getByText(/Fills after the first archived week finishes and you run make refresh/)).toBeTruthy();
    expect(screen.getByText(/Archived now: week 7/)).toBeTruthy();
  });
  test("marks the best model in text and warns about small samples", () => {
    const rows = [row({}), row({ model: "baseline", mae: 4.9 }), row({ week: null }), row({ week: null, model: "baseline", mae: 4.9 }), row({ week: null, position: "WR", n: 10 })];
    render(<ScorecardView data={data(rows)} />);
    expect(screen.getAllByText(/4\.9 best/).length).toBeGreaterThan(0);
    expect(screen.getByRole("note").textContent).toMatch(/fewer than 30/);
    expect(screen.getByText(/Lower error is better; points are fantasy points per player-game/)).toBeTruthy();
    expect(screen.getByText(/Sleeper: not clean/)).toBeTruthy();
  });
  test("shows the by-week bars only with more than one week", () => {
    const one = render(<ScorecardView data={data([row({})])} />);
    expect(screen.queryByRole("list", { name: "Average error by week" })).toBeNull();
    one.unmount();
    render(<ScorecardView data={data([row({}), row({ week: 8 })], [7, 8])} />);
    expect(screen.getByRole("list", { name: "Average error by week" })).toBeTruthy();
  });
});
