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
  partner: "Rivals",
  give: "A (RB)",
  get: "B (WR)",
  give_ids: ["a"],
  get_ids: ["b"],
  kind: "need swap",
  my_fills: "WR",
  their_fills: "RB",
  my_fit: 12.5,
  their_fit: 4.2,
  my_playoff: 0.021,
  my_title: 0.012,
  their_playoff: 0.013,
  their_title: 0.004,
  se_title: 0.0031,
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
    mockFetch(() =>
      ++calls === 1
        ? { status: "error", error: { code: "busy", message: "The server is busy. Try again in a moment." } }
        : { status: "ok", data: [FOUND] },
    );
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
const asset = (id: string, name: string): Asset => ({
  gsis_id: id,
  full_name: name,
  position: "RB",
  ros_points: 100,
  label: `${name} (RB, 100 pts)`,
});
const SIDE = {
  roster_id: 1,
  playoff_before: 0.5,
  playoff_after: 0.55,
  title_before: 0.1,
  title_after: 0.12,
  wins_before: 8,
  wins_after: 8.4,
};
const RESULT = {
  odds: [
    { ...SIDE, side: "me", team_name: "Mine" },
    { ...SIDE, side: "them", roster_id: 2, team_name: "Rivals" },
  ],
  roster_changes: [{ team_name: "Rivals", action: "dropped", full_name: "Zed", position: "WR" }],
  warning: "Automatic roster moves to keep sizes equal:",
  trade_deadline: 11,
  market: { give_value: 5000, get_value: 5000, hint: "even", fetched_at: "2026-10-25T08:00:00+00:00" },
};

async function evaluate(reply: Reply, debounceMs = 0) {
  const fn = mockFetch((url) => (url.includes("trade-assets") ? { status: "ok", data: [asset("t1", "Theirs")] } : reply));
  wrap(<Evaluator league="L" partners={PARTNERS} mine={[asset("m1", "Mine")]} debounceMs={debounceMs} />);
  await userEvent.click(screen.getByRole("checkbox", { name: /Mine/ }));
  await userEvent.click(await screen.findByRole("checkbox", { name: /Theirs/ }));
  return fn;
}

const evaluateCalls = (fn: ReturnType<typeof mockFetch>) => fn.mock.calls.filter(([u]) => String(u).includes("trades/evaluate"));

describe("trade builder", () => {
  it("has no Evaluate button and asks for a player on each side until both have one", () => {
    mockFetch(() => ({ status: "ok", data: [] }));
    wrap(<Evaluator league="L" partners={PARTNERS} mine={[asset("m1", "Mine")]} debounceMs={0} />);
    expect(screen.queryByRole("button", { name: "Evaluate" })).toBeNull();
    expect(screen.getByText("Pick at least one player on each side.")).toBeInTheDocument();
  });
  it("evaluates on its own once both sides have a player, and shows both sides, the warning and the market", async () => {
    const fn = await evaluate({ status: "ok", data: RESULT });
    expect(await screen.findByText("Automatic roster moves to keep sizes equal:")).toBeInTheDocument();
    expect(evaluateCalls(fn)).toHaveLength(1);
    expect(screen.getByText("Zed")).toBeInTheDocument();
    expect(screen.getAllByRole("img", { name: /Make playoffs: 50.0% before, 55.0% after/ })).toHaveLength(2);
    expect(screen.getByText("Trade deadline: week 11.")).toBeInTheDocument();
    expect(screen.getByText(/Market value \(2026-10-25\): gives 5,000, gets 5,000, even/)).toBeInTheDocument();
  });
  it("sends one request for a burst of changes, not one per click", async () => {
    mockFetch((url) =>
      url.includes("trade-assets") ? { status: "ok", data: [asset("t1", "Theirs"), asset("t2", "Other")] } : { status: "ok", data: RESULT },
    );
    const fn = vi.mocked(fetch);
    wrap(<Evaluator league="L" partners={PARTNERS} mine={[asset("m1", "Mine")]} debounceMs={300} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /Mine/ }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /Theirs/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /Other/ }));
    await screen.findByText("Trade deadline: week 11.");
    expect(evaluateCalls(fn)).toHaveLength(1);
  });
  it("dims the previous result and marks it busy while the picks are still settling", async () => {
    mockFetch((url) =>
      url.includes("trade-assets") ? { status: "ok", data: [asset("t1", "Theirs"), asset("t2", "Other")] } : { status: "ok", data: RESULT },
    );
    wrap(<Evaluator league="L" partners={PARTNERS} mine={[asset("m1", "Mine")]} debounceMs={300} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /Mine/ }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /Theirs/ }));
    await screen.findByText("Trade deadline: week 11.");
    const live = screen.getByTestId("trade-result");
    expect(live).toHaveAttribute("aria-live", "polite");
    expect(live).toHaveAttribute("aria-busy", "false");
    await userEvent.click(screen.getByRole("checkbox", { name: /Other/ }));
    expect(live).toHaveAttribute("aria-busy", "true");
    await waitFor(() => expect(live).toHaveAttribute("aria-busy", "false"));
  });
  it("keeps the newer result when an older response arrives late", async () => {
    let releaseFirst: () => void = () => {};
    const gate = new Promise<void>((r) => (releaseFirst = r));
    const stale = { ...RESULT, trade_deadline: 3 };
    const fresh = { ...RESULT, trade_deadline: 12 };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.includes("trade-assets"))
          return new Response(JSON.stringify(envelope({ status: "ok", data: [asset("t1", "Theirs"), asset("t2", "Other")] })));
        const second = String(init?.body).includes("t2");
        if (!second) await gate;
        return new Response(JSON.stringify(envelope({ status: "ok", data: second ? fresh : stale })));
      }),
    );
    wrap(<Evaluator league="L" partners={PARTNERS} mine={[asset("m1", "Mine")]} debounceMs={0} />);
    await userEvent.click(screen.getByRole("checkbox", { name: /Mine/ }));
    await userEvent.click(await screen.findByRole("checkbox", { name: /Theirs/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /Other/ }));
    expect(await screen.findByText("Trade deadline: week 12.")).toBeInTheDocument();
    releaseFirst();
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.getByText("Trade deadline: week 12.")).toBeInTheDocument();
    expect(screen.queryByText("Trade deadline: week 3.")).toBeNull();
  });
  it("shows the partner's change beside mine and the pitch with a copy button when both gain", async () => {
    await evaluate({ status: "ok", data: RESULT });
    expect(await screen.findByRole("region", { name: "Both sides" })).toHaveTextContent("Mine");
    expect(screen.getByRole("region", { name: "Both sides" })).toHaveTextContent("Rivals");
    expect((screen.getByLabelText("Message to copy") as HTMLTextAreaElement).value).toContain("my Mine for your Theirs");
    expect(screen.getByRole("button", { name: "Copy message" })).toBeInTheDocument();
  });
  it("offers no pitch when the partner does not gain", async () => {
    const worse = { ...RESULT, odds: [RESULT.odds[0], { ...RESULT.odds[1], playoff_after: 0.4 }] };
    await evaluate({ status: "ok", data: worse });
    await screen.findByRole("region", { name: "Both sides" });
    expect(screen.queryByLabelText("Message to copy")).toBeNull();
    expect(screen.getByText(/does not raise both teams/)).toBeInTheDocument();
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
