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
  gsis_id: "a", full_name: "Ann", position: "WR", week: 9, projection: 11, p10: 4, median: 12, p90: 21, chance_to_play: 0.76,
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

function renderSections() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TeamContext.Provider value={{ team: 2, league: "a", teams: [], viewed: null, setTeam: () => {}, notice: null, dismissNotice: () => {} }}>
        <MemoryRouter>
          <PlayerSections gsisId="a" />
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
    expect(screen.getByText(/Free Guy/)).toBeInTheDocument();
    expect(screen.getByText(/teammates who carry targets are out/)).toBeInTheDocument();
    expect(screen.getByText(/Questionable \(hamstring\)/)).toBeInTheDocument();
    expect(screen.getByText(/4200/)).toBeInTheDocument();
    expect(screen.getByText(/Owned by Theirs/)).toBeInTheDocument();
    expect(screen.getByText(/Snap share/)).toBeInTheDocument();
    expect(screen.getByText(/Target share/)).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: /^Form:/ })).toHaveLength(2);
  });

  it("says not available for the next game and rest of season, and hides role, why and injury, when the data is missing", () => {
    mock(ready({ ...profile, median: null, p10: null, p90: null, projection: null, ros_points: null, ros_over_replacement: null, replacement_name: null, replacement_points: null,
      role_weeks: [], why: null, outlook_label: null, injury: null, injury_note: null, chance_to_play: null }), ready([]), ready({ rows: [], unmatched: 0 }));
    renderSections();
    expect(headings()).toEqual(["Next game", "Rest of season", "Market value", "Owner"]);
    expect(screen.getAllByText(/Not available/).length).toBe(3);
    expect(screen.getByText("Free agent")).toBeInTheDocument();
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
