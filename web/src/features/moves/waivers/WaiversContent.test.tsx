import { render, screen, within } from "@testing-library/react";
import { leaguePath, onlyRoutes } from "@/test/fakeApi";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import type { ApiState } from "@/api/envelope";
import { WaiversContent } from "./WaiversView";

const paths: string[] = [];
const leagueRow = { league_key: "a", league_id: "9", name: "L", current_week: 9, playoff_week_start: 15, playoff_weeks: 3 };
vi.mock("@/lib/league", () => ({
  useLeague: () => ({ league: "a", leagues: { kind: "ready", data: [leagueRow] } }),
  useLeagueRow: () => leagueRow,
  useLeagueApi: (route: string, query?: object) => {
    const path = leaguePath(route, query);
    paths.push(path);
    const none: ApiState<unknown> = { kind: "ready", data: [] };
    return onlyRoutes({
      waivers: none,
      "waivers?horizon=playoffs": none,
      "streamers?kind=DEF": none,
      "streamers?kind=K": none,
      stash: { kind: "ready", data: { open_ir_slots: 0, rows: [] } },
    })(path);
  },
}));
vi.mock("@/lib/who", () => ({ useWho: () => ({ name: null }), whoFor: () => ({ name: null }) }));
vi.mock("@/api/useEnvelope", () => ({ useEnvelopeQuery: () => ({ kind: "loading" }) }));

type Params = Parameters<typeof WaiversContent>[0];
const renderWith = (params: Partial<Params> = {}) => {
  const props: Params = { rank: "ros", onRank: vi.fn(), pos: null, onShowAll: vi.fn(), ...params };
  render(
    <MemoryRouter>
      <WaiversContent {...props} />
    </MemoryRouter>,
  );
  return props;
};
const toggle = () => screen.getByRole("radiogroup", { name: "Rank adds by" });

beforeEach(() => {
  paths.length = 0;
});

describe("WaiversContent rank", () => {
  it("fetches rest of season by default", () => {
    renderWith();
    expect(paths).toContain("waivers");
    expect(paths.some((p) => p.includes("horizon"))).toBe(false);
    expect(within(toggle()).getByRole("radio", { name: "Rest of season" })).toBeChecked();
  });
  it("ranks by playoff weeks: refetches with the horizon and names the weeks", () => {
    renderWith({ rank: "playoffs" });
    expect(paths).toContain("waivers?horizon=playoffs");
    expect(within(toggle()).getByRole("radio", { name: "Playoff weeks" })).toBeChecked();
    expect(screen.getByText("Ranked by playoff weeks 15 to 17, 0 adds")).toBeInTheDocument();
    expect(paths).toContain("streamers?kind=K");
  });
  it("hands the choice to its page", async () => {
    const { onRank } = renderWith();
    await userEvent.click(within(toggle()).getByRole("radio", { name: "Playoff weeks" }));
    expect(onRank).toHaveBeenCalledWith("playoffs");
  });
});

describe("WaiversContent position", () => {
  it("Show all asks the page to drop the position", async () => {
    const { onShowAll } = renderWith({ pos: "RB" });
    await userEvent.click(screen.getByRole("button", { name: "Show all" }));
    expect(onShowAll).toHaveBeenCalled();
  });
});
