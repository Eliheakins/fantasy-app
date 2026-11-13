import { render, screen, within } from "@testing-library/react";
import type { ApiState } from "@/api/envelope";
import { leaguePath, onlyRoutes } from "@/test/fakeApi";
import type { BracketData, BracketMatch } from "@/lib/outlookTypes";
import { BracketSection } from "./BracketSection";

let state: ApiState<BracketData>;
vi.mock("@/lib/league", () => ({ useLeagueApi: (route: string) => onlyRoutes({ bracket: state })(leaguePath(route)) }));

const side = (
  roster_id: number | null,
  team_name: string | null,
  seed: number | null,
  from_kind: string | null = null,
  from_m: number | null = null,
) => ({
  roster_id,
  team_name,
  seed,
  from_kind,
  from_m,
});
const match = (over: Partial<BracketMatch> = {}): BracketMatch => ({
  m: 1,
  place: null,
  winner: null,
  t1: side(3, "Aces", 3),
  t2: side(6, "Bears", 6),
  t1_p_win: 0.58,
  t2_p_win: 0.42,
  is_mine: false,
  ...over,
});
const ready = (rounds: BracketData["rounds"]) => {
  state = { kind: "ready", data: { rounds } };
};
const seeded = [
  { round: 1, weeks: [15], matches: [match()] },
  {
    round: 2,
    weeks: [16],
    matches: [match({ m: 2, place: 1, t1: side(null, null, null, "w", 1), t2: side(1, "Cubs", 1), t1_p_win: null, t2_p_win: null })],
  },
];

describe("BracketSection", () => {
  it("is hidden when there is no bracket yet", () => {
    state = { kind: "no_data", message: "x" };
    const { container } = render(<BracketSection myRosterId={1} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows an error with retry-able alert", () => {
    state = { kind: "error", error: { message: "boom", code: null } };
    render(<BracketSection myRosterId={1} />);
    expect(screen.getByRole("alert")).toHaveTextContent("boom");
  });

  it("lists rounds as headings and matches as list items, with text only", () => {
    ready(seeded);
    render(<BracketSection myRosterId={1} />);
    expect(screen.getByRole("heading", { name: "Playoff bracket" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Round 1, week 15" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Round 2, week 16" })).toBeInTheDocument();
    expect(screen.getAllByRole("list")).toHaveLength(2);
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.queryByRole("grid")).toBeNull();
    expect(screen.getByText("Seed 3 Aces vs seed 6 Bears. Aces 58% to advance, Bears 42%.")).toBeInTheDocument();
  });

  it("says who won a played match, names undecided sides and marks me", () => {
    ready([{ round: 1, weeks: [15], matches: [match({ winner: 3 })] }, seeded[1]!]);
    render(<BracketSection myRosterId={1} />);
    expect(screen.getByText("Seed 3 Aces vs seed 6 Bears. Aces won.")).toBeInTheDocument();
    const second = screen.getAllByRole("listitem")[1]!;
    expect(within(second).getByText(/Winner of match 1 vs seed 1 Cubs \(you\)\./)).toBeInTheDocument();
  });

  it("heads the section with Champion or Eliminated", () => {
    ready([{ round: 1, weeks: [15], matches: [match({ place: 1, winner: 3 })] }]);
    const { unmount } = render(<BracketSection myRosterId={3} />);
    expect(screen.getByText("Champion")).toBeInTheDocument();
    unmount();
    render(<BracketSection myRosterId={6} />);
    expect(screen.getByText("Eliminated in round 1")).toBeInTheDocument();
  });
});
