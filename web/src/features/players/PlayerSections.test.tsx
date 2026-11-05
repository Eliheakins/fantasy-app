import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ApiState } from "@/api/envelope";
import { useApi } from "@/hooks/useApi";
import { TeamContext } from "@/lib/teamContext";
import { PlayerSections } from "./PlayerSections";
import type { PlayerProfile } from "./profile";

vi.mock("@/hooks/useApi", () => ({ useApi: vi.fn() }));

const profile: PlayerProfile = {
  gsis_id: "a", full_name: "Ann", position: "WR", week: 9, result_week: null, result_points: null, is_out: false, projection: 11, p10: 4, median: 12, p90: 21, chance_to_play: 0.76,
  injury: "Questionable", injury_note: "Questionable (hamstring)", ros_points: 80, replacement_name: "Free Guy", replacement_points: 62.5,
  ros_over_replacement: 17.5, outlook_label: "Improving", why: "teammates who carry targets are out",
  role_weeks: [{ week: 1, snap_share: 0.8, target_share: 0.2 }, { week: 2, snap_share: 0.6, target_share: 0.3 }],
};
const market = [{ gsis_id: "a", value: 4200, overall_rank: 12, position_rank: 5, trend_30_day: -150, fetched_at: "2026-11-04" }];
const owners = { rows: [{ gsis_id: "a", owner: "Theirs", roster_id: 3, is_mine: false }], unmatched: 0 };
const ready = <T,>(data: T): ApiState<T> => ({ kind: "ready", data }) as ApiState<T>;

function mock(p: ApiState<unknown>, m: ApiState<unknown> = ready(market), o: ApiState<unknown> = ready(owners)) {
  vi.mocked(useApi).mockImplementation(((path: string | null) =>
    path?.includes("/profile") ? p : path?.includes("/market-values") ? m : path?.includes("/owners") ? o : { kind: "loading" }) as typeof useApi);
}

function renderSections(level: 2 | 3 = 2) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TeamContext.Provider value={{ team: 2, league: "a", teams: [], viewed: null, setTeam: () => {}, notice: null, dismissNotice: () => {} }}>
        <MemoryRouter>
          <PlayerSections gsisId="a" level={level} name="Ann" />
        </MemoryRouter>
      </TeamContext.Provider>
    </QueryClientProvider>,
  );
}
const headings = () => screen.getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
afterEach(() => vi.resetAllMocks());

describe("PlayerSections", () => {
  it("shows every section in the plan's order when the data exists", () => {
    mock(ready(profile));
    renderSections();
    expect(headings()).toEqual(["Next game", "Rest of season", "Role", "Why the model expects change", "Injury and chance to play", "Market value", "Owner"]);
    expect(screen.getByText(/12\.0/)).toBeInTheDocument();
    expect(screen.getByText(/\+17\.5/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /\+17\.5.*what drives this/ })).toBeInTheDocument();
    expect(screen.getByText(/Free Guy/)).toBeInTheDocument();
    expect(screen.getByText(/teammates who carry targets are out/)).toBeInTheDocument();
    expect(screen.getByText(/Questionable \(hamstring\)/)).toBeInTheDocument();
    expect(screen.getByText(/4200/)).toBeInTheDocument();
    expect(screen.getByText(/Owned by Theirs/)).toBeInTheDocument();
    expect(screen.getByText("Snap share")).toBeInTheDocument();
    expect(screen.getByText("Target share")).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: /by week, percent:/ })).toHaveLength(2);
  });

  it("says not available for the next game and rest of season, and hides role, why and injury, when the data is missing", () => {
    mock(ready({ ...profile, median: null, p10: null, p90: null, projection: null, ros_points: null, ros_over_replacement: null, replacement_name: null, replacement_points: null,
      role_weeks: [], why: null, outlook_label: null, injury: null, injury_note: null, chance_to_play: null }), ready([]), ready({ rows: [], unmatched: 0 }));
    renderSections();
    expect(headings()).toEqual(["Next game", "Rest of season", "Market value", "Owner"]);
    expect(screen.getAllByText(/Not available/).length).toBe(3);
    expect(screen.getByText("Free agent")).toBeInTheDocument();
  });

  it("shows the final result with next week's range", () => {
    mock(ready({ ...profile, result_week: 8, result_points: 17.3 }));
    renderSections();
    expect(screen.getByText("Week 8: 17.3 points, final.")).toBeInTheDocument();
    expect(screen.getByText(/median points, week 9/)).toBeInTheDocument();
  });

  it("shows only the result when no later week is projected", () => {
    mock(ready({ ...profile, result_week: 8, result_points: 17.3, week: null, median: null, p10: null, p90: null }));
    renderSections();
    expect(screen.getByText("Week 8: 17.3 points, final.")).toBeInTheDocument();
    expect(screen.queryByText(/Not available: this player has no projection/)).toBeNull();
  });

  it("hides target share for a QB and the whole role section for a K, and labels each sparkline by name", () => {
    mock(ready({ ...profile, position: "QB" }));
    renderSections();
    expect(screen.queryByText("Target share")).toBeNull();
    expect(screen.getByRole("img", { name: "Snap share by week, percent: 80.0, 60.0" })).toBeInTheDocument();
  });

  it("hides role for a kicker", () => {
    mock(ready({ ...profile, position: "K" }));
    renderSections();
    expect(screen.queryByRole("heading", { name: "Role" })).toBeNull();
  });

  it("does not show a 30-day change as large as the value", () => {
    mock(ready(profile), ready([{ ...market[0], value: 600, trend_30_day: 620 }]));
    renderSections();
    expect(screen.queryByText(/, 30-day change/)).toBeNull();
    expect(screen.getByText(/had no value 30 days ago/)).toBeInTheDocument();
  });

  it("says when the player is out in the rest of season line", () => {
    mock(ready({ ...profile, is_out: true }));
    renderSections();
    expect(screen.getByText(/He is out/)).toBeInTheDocument();
  });

  it("uses h3 sections under a compare column and names the player in the range bar", () => {
    mock(ready(profile));
    renderSections(3);
    expect(screen.queryAllByRole("heading", { level: 2 })).toHaveLength(0);
    expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(7);
    expect(screen.getByRole("img", { name: /^Ann, next game:/ })).toBeInTheDocument();
  });

  it("states that market value history is not stored", () => {
    mock(ready(profile));
    renderSections();
    expect(screen.getByText(/history is not stored/i)).toBeInTheDocument();
  });

  it("shows the error when the profile fails to load", () => {
    mock({ kind: "error", error: { message: "boom", code: null }, retry: () => {} } as ApiState<never>);
    renderSections();
    expect(screen.getByText(/boom/)).toBeInTheDocument();
  });
});
