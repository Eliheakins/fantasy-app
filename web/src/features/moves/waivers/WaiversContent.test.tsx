import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import type { ApiState } from "@/api/envelope";
import { WaiversContent } from "./WaiversView";

const paths: string[] = [];
const leagueRow = { league_key: "a", league_id: "9", name: "L", current_week: 9, playoff_week_start: 15, playoff_weeks: 3 };
vi.mock("@/lib/league", () => ({
  useLeague: () => ({ league: "a", leagues: { kind: "ready", data: [leagueRow] } }),
  useLeagueRow: () => leagueRow,
  useLeagueApi: (path: string): ApiState<never[]> => {
    paths.push(path);
    return { kind: "ready", data: path === "stash" ? { open_ir_slots: 0, rows: [] } : [] } as ApiState<never[]>;
  },
}));
vi.mock("@/lib/who", () => ({ useWho: () => ({ name: null }), whoFor: () => ({ name: null }) }));
vi.mock("@/api/useEnvelope", () => ({ useEnvelopeQuery: () => ({ kind: "loading" }) }));

function Where() {
  return <p data-testid="search">{useLocation().search}</p>;
}
const renderAt = (entry: string) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <WaiversContent />
      <Where />
    </MemoryRouter>,
  );
const toggle = () => screen.getByRole("radiogroup", { name: "Rank adds by" });

beforeEach(() => {
  paths.length = 0;
});

describe("WaiversContent rank param", () => {
  it("fetches rest of season by default", () => {
    renderAt("/moves");
    expect(paths).toContain("waivers");
    expect(paths.some((p) => p.includes("horizon"))).toBe(false);
    expect(within(toggle()).getByRole("radio", { name: "Rest of season" })).toBeChecked();
  });
  it("reads ?rank=playoffs, refetches with the horizon and names the weeks", () => {
    renderAt("/moves?rank=playoffs");
    expect(paths).toContain("waivers?horizon=playoffs");
    expect(within(toggle()).getByRole("radio", { name: "Playoff weeks" })).toBeChecked();
    expect(screen.getByText("Ranked by playoff weeks 15 to 17, 0 adds")).toBeInTheDocument();
    expect(paths).toContain("streamers?kind=K");
  });
  it("writes the choice to the URL and removes it for rest of season", async () => {
    renderAt("/moves?league=a");
    await userEvent.click(within(toggle()).getByRole("radio", { name: "Playoff weeks" }));
    expect(screen.getByTestId("search")).toHaveTextContent("rank=playoffs");
    expect(screen.getByTestId("search")).toHaveTextContent("league=a");
    await userEvent.click(within(toggle()).getByRole("radio", { name: "Rest of season" }));
    expect(screen.getByTestId("search")).not.toHaveTextContent("rank");
  });
});

describe("WaiversContent position param", () => {
  it("Show all removes ?pos= and keeps the other params", async () => {
    renderAt("/moves?league=a&pos=RB");
    await userEvent.click(screen.getByRole("button", { name: "Show all" }));
    expect(screen.getByTestId("search")).not.toHaveTextContent("pos");
    expect(screen.getByTestId("search")).toHaveTextContent("league=a");
  });
});
