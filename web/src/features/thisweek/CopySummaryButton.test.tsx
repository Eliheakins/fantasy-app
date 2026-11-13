import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { CopySummaryButton } from "./CopySummaryButton";
import { copyText } from "@/lib/clipboard";
import type { Todo } from "./todos";

vi.mock("@/lib/clipboard", () => ({ copyText: vi.fn() }));

const ok = (data: unknown) => ({ status: "ok", data, error: null, started_at: null });
const digest = ok({
  last_week: {
    week: 9,
    roster_id: 1,
    team_name: "Me",
    opponent: "Rivals",
    points: 100,
    opp_points: 90,
    result: "W",
    bench_points_left: null,
    luck: null,
  },
  odds_change: [
    {
      roster_id: 1,
      team_name: "Me",
      is_me: true,
      as_of_week: 10,
      prev_as_of_week: 9,
      p_playoffs: 0.5,
      p_title: 0.1,
      d_playoffs: 0.05,
      d_title: 0,
    },
  ],
});
const routes: Record<string, unknown> = {
  "/api/leagues": ok([{ league_key: "a", name: "Alpha", roster_id: 1, current_week: 10 }]),
  "/api/leagues/a/digest": digest,
};
const todos: Todo[] = [
  {
    id: "t",
    leagueKey: "a",
    leagueName: "Alpha",
    kind: "waiver",
    title: "Add X",
    detail: "",
    href: "/",
    effect: { playoffPoints: 1, points: null },
    deadlineDay: null,
    sleeperUrl: null,
  },
];

const show = (pending = false) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <CopySummaryButton todos={todos} pending={pending} />
    </QueryClientProvider>,
  );

beforeEach(() => {
  routes["/api/leagues/a/digest"] = digest;
  vi.mocked(copyText).mockReset();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => new Response(JSON.stringify(routes[new URL(url, "http://x").pathname]))),
  );
});
afterEach(() => vi.unstubAllGlobals());

const ready = async () => {
  const button = screen.getByRole("button", { name: "Copy summary" });
  await waitFor(() => expect(button).toBeEnabled());
  return button;
};

describe("CopySummaryButton", () => {
  it("copies the text and announces the line count", async () => {
    vi.mocked(copyText).mockResolvedValue(true);
    show();
    fireEvent.click(await ready());
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/^Copied 3 lines\.$/));
    expect(vi.mocked(copyText).mock.calls[0]?.[0]).toContain("Alpha: W 100.0 to 90.0 vs Rivals");
  });
  it("says a league whose digest failed could not load", async () => {
    vi.mocked(copyText).mockResolvedValue(true);
    routes["/api/leagues/a/digest"] = { status: "error", data: null, error: { message: "boom", code: null }, started_at: null };
    show();
    fireEvent.click(await ready());
    await waitFor(() => expect(vi.mocked(copyText)).toHaveBeenCalled());
    expect(vi.mocked(copyText).mock.calls[0]?.[0]).toContain("Alpha: could not load");
  });
  it("shows the text selected in a textarea when copying fails", async () => {
    vi.mocked(copyText).mockResolvedValue(false);
    show();
    fireEvent.click(await ready());
    const box = await screen.findByRole("textbox", { name: "Weekly summary" });
    expect(box).toHaveAttribute("readonly");
    expect(box).toHaveFocus();
    expect(screen.getByRole("status")).toHaveTextContent("Could not copy. The text is selected.");
  });
  it("is disabled with a reason while to-dos are pending", () => {
    show(true);
    expect(screen.getByRole("button", { name: "Copy summary" })).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("Waiting for your to-dos to load.");
  });
});
