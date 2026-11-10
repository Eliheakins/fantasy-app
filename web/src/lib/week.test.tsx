import { act, render, renderHook, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { createMemoryRouter, MemoryRouter, RouterProvider, useLocation } from "react-router-dom";
import { clampWeek, usePageEyebrow, useWeek } from "./week";

vi.mock("@/lib/league", () => ({
  useLeague: () => ({ league: "a", leagues: { kind: "ready", data: [{ league_key: "a", name: "Colgate ", current_week: 9 }] } }),
}));

const wrap =
  (entry: string) =>
  ({ children }: { children: ReactNode }) => <MemoryRouter initialEntries={[entry]}>{children}</MemoryRouter>;

function renderWeek(entry: string) {
  return renderHook(() => ({ ...useWeek(), location: useLocation() }), { wrapper: wrap(entry) });
}

describe("useWeek", () => {
  it("defaults to the league's current week", () => {
    expect(renderWeek("/lineup?league=a").result.current.week).toBe(9);
  });

  it("reads ?week=", () => {
    expect(renderWeek("/lineup?week=4").result.current.week).toBe(4);
  });

  it("ignores a week outside 1 to 18 or not a number", () => {
    expect(renderWeek("/lineup?week=40").result.current.week).toBe(9);
    expect(renderWeek("/lineup?week=abc").result.current.week).toBe(9);
  });

  it("setWeek writes ?week= and keeps the other params", () => {
    const { result } = renderWeek("/lineup?league=a&team=2");
    act(() => result.current.setWeek(12));
    expect(result.current.week).toBe(12);
    const params = new URLSearchParams(result.current.location.search);
    expect(params.get("week")).toBe("12");
    expect(params.get("team")).toBe("2");
    expect(params.get("league")).toBe("a");
  });
});

describe("usePageEyebrow", () => {
  const eyebrow = (entry: string, followsWeek?: boolean) =>
    renderHook(() => usePageEyebrow("Moves", followsWeek), { wrapper: wrap(entry) }).result.current;

  it("shows the current week on a page that ignores ?week=", () => {
    expect(eyebrow("/moves?week=4")).toBe("Moves · Week 9 · Colgate");
  });

  it("shows the selected week on a page that follows it", () => {
    expect(eyebrow("/season?week=4", true)).toBe("Moves · Week 4 · Colgate");
  });
});

describe("setWeek history", () => {
  it("replaces the entry instead of pushing a new one", async () => {
    function Probe() {
      const { setWeek } = useWeek();
      return <button onClick={() => setWeek(3)}>set</button>;
    }
    const router = createMemoryRouter([{ path: "*", element: <Probe /> }], { initialEntries: ["/lineup"] });
    render(<RouterProvider router={router} />);
    await userEvent.click(screen.getByText("set"));
    expect(router.state.location.search).toBe("?week=3");
    expect(router.state.historyAction).toBe("REPLACE");
  });
});

test("clampWeek keeps a week inside the season", () => {
  expect([clampWeek(0), clampWeek(7), clampWeek(30)]).toEqual([1, 7, 18]);
});
