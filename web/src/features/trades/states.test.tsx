import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { Evaluator } from "./Evaluator";
import { FindTradesSection } from "./FindTrades";
import type { Asset, Partner } from "./types";

type Reply = { status: string; data?: unknown; error?: { code: string; message: string }; started_at?: string };
const envelope = (r: Reply) => ({ data: null, error: null, started_at: null, ...r });

function mockFetch(handler: (url: string, init?: RequestInit) => Reply) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => new Response(JSON.stringify(envelope(handler(url, init)))));
  vi.stubGlobal("fetch", fn);
  return fn;
}

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

afterEach(() => vi.unstubAllGlobals());

const FOUND = {
  partner: "Rivals", give: "A (RB)", get: "B (WR)", give_ids: ["a"], get_ids: ["b"],
  kind: "need swap", my_fills: "WR", their_fills: "RB", my_fit: 12.5, their_fit: 4.2,
  my_playoff: 0.021, my_title: 0.012, their_playoff: 0.013, their_title: 0.004, se_title: 0.0031,
  market: { give_value: 5000, get_value: 5700, hint: "you receive 14% more", fetched_at: "2026-10-25T08:00:00+00:00" },
};

describe("find trades", () => {
  it("shows the running job with elapsed time", async () => {
    mockFetch(() => ({ status: "running", started_at: new Date(Date.now() - 12000).toISOString() }));
    wrap(<FindTradesSection league="L" />);
    await userEvent.click(screen.getByRole("button", { name: "Find trades" }));
    expect(await screen.findByText(/1\d s so far/)).toBeInTheDocument();
  });
  it("shows the table when done", async () => {
    mockFetch(() => ({ status: "ok", data: [FOUND] }));
    wrap(<FindTradesSection league="L" />);
    await userEvent.click(screen.getByRole("button", { name: "Find trades" }));
    expect(await screen.findByText("Rivals")).toBeInTheDocument();
    expect(screen.getByText("0.31")).toBeInTheDocument();
    expect(screen.getByText("+2.1 ▲")).toBeInTheDocument();
    expect(screen.getByText("You fill: WR")).toBeInTheDocument();
    expect(screen.getByText("They fill: RB")).toBeInTheDocument();
    expect(screen.getByText("need swap")).toBeInTheDocument();
    expect(screen.getByText(/gives 5,000, gets 5,700/)).toBeInTheDocument();
    expect(screen.getByText(/you receive 14% more/)).toBeInTheDocument();
    expect(screen.getByText(/2026-10-25/)).toBeInTheDocument();
  });
  it("shows no market text when the values are missing", async () => {
    mockFetch(() => ({ status: "ok", data: [{ ...FOUND, market: null }] }));
    wrap(<FindTradesSection league="L" />);
    await userEvent.click(screen.getByRole("button", { name: "Find trades" }));
    expect(await screen.findByText("Rivals")).toBeInTheDocument();
    expect(screen.queryByText(/gives \d/)).toBeNull();
  });
  it("says so when nothing helps both teams", async () => {
    mockFetch(() => ({ status: "ok", data: [] }));
    wrap(<FindTradesSection league="L" />);
    await userEvent.click(screen.getByRole("button", { name: "Find trades" }));
    expect(await screen.findByText(/No trade fills a need for both teams right now/)).toBeInTheDocument();
  });
  it("offers a retry on busy, and retrying works", async () => {
    let calls = 0;
    mockFetch(() => (++calls === 1 ? { status: "error", error: { code: "busy", message: "The server is busy. Try again in a moment." } } : { status: "ok", data: [FOUND] }));
    wrap(<FindTradesSection league="L" />);
    await userEvent.click(screen.getByRole("button", { name: "Find trades" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The server is busy");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Rivals")).toBeInTheDocument();
  });
  it("shows the deadline message as an amber notice without retry", async () => {
    mockFetch(() => ({ status: "error", error: { code: "invalid", message: "The trade deadline has passed." } }));
    wrap(<FindTradesSection league="L" />);
    await userEvent.click(screen.getByRole("button", { name: "Find trades" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The trade deadline has passed.");
    expect(screen.queryByRole("button", { name: "Try again" })).toBeNull();
  });
});

const PARTNERS: Partner[] = [{ roster_id: 2, team_name: "Rivals" }];
const asset = (id: string, name: string): Asset => ({ gsis_id: id, full_name: name, position: "RB", ros_points: 100, label: `${name} (RB, 100 pts)` });
const SIDE = { roster_id: 1, playoff_before: 0.5, playoff_after: 0.55, title_before: 0.1, title_after: 0.12, wins_before: 8, wins_after: 8.4 };
const RESULT = {
  odds: [{ ...SIDE, side: "me", team_name: "Mine" }, { ...SIDE, side: "them", roster_id: 2, team_name: "Rivals" }],
  roster_changes: [{ team_name: "Rivals", action: "dropped", full_name: "Zed", position: "WR" }],
  warning: "Automatic roster moves to keep sizes equal:",
  trade_deadline: 11,
  market: { give_value: 5000, get_value: 5000, hint: "even", fetched_at: "2026-10-25T08:00:00+00:00" },
};

async function evaluate(reply: Reply) {
  mockFetch((url) => (url.includes("trade-assets") ? { status: "ok", data: [asset("t1", "Theirs")] } : reply));
  wrap(<Evaluator league="L" partners={PARTNERS} mine={[asset("m1", "Mine")]} />);
  await userEvent.click(screen.getByRole("checkbox", { name: /Mine/ }));
  await userEvent.click(await screen.findByRole("checkbox", { name: /Theirs/ }));
  await userEvent.click(screen.getByRole("button", { name: "Evaluate" }));
}

describe("evaluator", () => {
  it("keeps Evaluate disabled until both sides have a player", () => {
    mockFetch(() => ({ status: "ok", data: [] }));
    wrap(<Evaluator league="L" partners={PARTNERS} mine={[asset("m1", "Mine")]} />);
    const button = screen.getByRole("button", { name: "Evaluate" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription("Pick at least one player on each side.");
  });
  it("shows both sides, the roster-moves warning with the partner's drop, and a text equivalent", async () => {
    await evaluate({ status: "ok", data: RESULT });
    expect(await screen.findByText("Automatic roster moves to keep sizes equal:")).toBeInTheDocument();
    expect(screen.getByText("Zed")).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: /Make playoffs: 50.0% before, 55.0% after/ })).toHaveLength(2);
    expect(screen.getAllByText("55.0%")).toHaveLength(4);
    expect(screen.getByText("Trade deadline: week 11.")).toBeInTheDocument();
    expect(screen.getByText(/Market value \(2026-10-25\): gives 5,000, gets 5,000, even/)).toBeInTheDocument();
  });
  it("shows the server's message as an amber notice", async () => {
    await evaluate({ status: "error", error: { code: "invalid", message: "The trade deadline has passed." } });
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("The trade deadline has passed."));
  });
  it("offers retry when busy", async () => {
    await evaluate({ status: "error", error: { code: "busy", message: "The server is busy. Try again in a moment." } });
    expect(await screen.findByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
