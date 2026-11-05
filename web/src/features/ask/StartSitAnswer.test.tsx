import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LeagueProvider } from "@/lib/league";
import type { LineupRow } from "@/features/lineup/logic";

import { StartSitAnswer } from "./StartSitAnswer";

const row = (id: string, o: Partial<LineupRow> = {}): LineupRow => ({
  slot: "TE", gsis_id: id, full_name: `Player ${id}`, position: "TE", projection: 10, p10: 4, p90: 18,
  starting_now: true, recommended: true, injury: null, injury_note: null, locked: false, actual: 0, game: "Sun", change: "", ...o,
});
const NAMES = { a: "Travis Kelce", b: "George Kittle" };
let lineup: LineupRow[] = [];

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const data = url.includes("/lineup") ? lineup : [{ league_key: "L1", name: "League", current_week: 9 }];
      return Response.json({ status: "ok", data, error: null, started_at: null });
    }),
  );
  window.localStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

function renderAnswer() {
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={["/ask?league=L1&team=2&q=x"]}>
        <LeagueProvider>
          <StartSitAnswer a="a" b="b" names={NAMES} />
        </LeagueProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("StartSitAnswer", () => {
  it("follows the lineup's recommended flag: one starter gives Start A over B with the gap in projected points", async () => {
    lineup = [row("a", { projection: 9, recommended: true }), row("b", { projection: 12.5, recommended: false })];
    renderAnswer();

    expect(await screen.findByText("Start Travis Kelce over George Kittle")).toBeTruthy();
    expect(screen.getByText(/-3\.5/).parentElement?.textContent).toMatch(/-3\.5 ▼ projected pts/);
    expect(screen.queryByText("toss-up")).toBeNull();
    expect(screen.getAllByRole("img")).toHaveLength(2);
    expect(screen.getByRole("link", { name: /Lineup/ }).getAttribute("href")).toBe("/lineup?league=L1&team=2");
  });

  it("shows a positive gap when the recommended player projects higher", async () => {
    lineup = [row("a", { projection: 9, recommended: false }), row("b", { projection: 11, recommended: true })];
    renderAnswer();

    expect(await screen.findByText("Start George Kittle over Travis Kelce")).toBeTruthy();
    expect(screen.getByText(/\+2\.0/).parentElement?.textContent).toMatch(/\+2\.0 ▲ projected pts/);
  });

  it("says the lineup starts both when both are recommended", async () => {
    lineup = [row("a"), row("b")];
    renderAnswer();

    expect(await screen.findByText("Your lineup starts both")).toBeTruthy();
    expect(screen.queryByText(/^Start /)).toBeNull();
  });

  it("says the lineup benches both, with who projects more", async () => {
    lineup = [row("a", { recommended: false, projection: 6 }), row("b", { recommended: false, projection: 8 })];
    renderAnswer();

    expect(await screen.findByText("Your lineup benches both")).toBeTruthy();
    expect(screen.getByText(/George Kittle projects more/)).toBeTruthy();
  });

  it("says a player is not on the roster and still shows the other player's range", async () => {
    lineup = [row("a")];
    renderAnswer();

    expect(await screen.findByText(/George Kittle is not on this team's roster/)).toBeTruthy();
    expect(screen.queryByText(/^Start /)).toBeNull();
    expect(screen.getAllByRole("img")).toHaveLength(1);
  });

  it("says so when neither player is on the roster", async () => {
    lineup = [row("z")];
    renderAnswer();

    expect(await screen.findByText(/Neither Travis Kelce nor George Kittle is on this team's roster/)).toBeTruthy();
  });

  it("withholds a recommendation when a game has started", async () => {
    lineup = [row("a", { locked: true, actual: 7.2 }), row("b")];
    renderAnswer();

    expect(await screen.findByText(/Travis Kelce's game has started/)).toBeTruthy();
    expect(screen.queryByText(/^Start /)).toBeNull();
    expect(screen.getAllByRole("img")).toHaveLength(2);
  });
});
