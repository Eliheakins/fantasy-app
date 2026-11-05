import { act, render, screen, fireEvent } from "@testing-library/react";
import type { TradeEvaluation } from "@/features/trades/types";
import { COPIED_NOTE_MS } from "./builder";
import { TradeOutcome } from "./TradeOutcome";

vi.mock("./builder", async (orig) => ({ ...(await orig<typeof import("./builder")>()), copyText: vi.fn().mockResolvedValue(true) }));

const side = (who: "me" | "them", name: string) => ({
  side: who, roster_id: 1, team_name: name, playoff_before: 0.5, playoff_after: 0.55,
  title_before: 0.1, title_after: 0.12, wins_before: 8, wins_after: 8.4,
});
const RESULT: TradeEvaluation = { odds: [side("me", "Mine"), side("them", "Rivals")], roster_changes: [], warning: null, trade_deadline: null, market: null };

describe("TradeOutcome explain", () => {
  it("each side change explains itself", () => {
    render(<TradeOutcome result={RESULT} give={["A"]} get={["B"]} />);
    expect(screen.getAllByRole("button", { name: /\+5\.0.*what drives this/ })).toHaveLength(2);
  });
});

describe("TradeOutcome pitch", () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => vi.useRealTimers());

  const copy = async () => {
    fireEvent.click(screen.getByRole("button", { name: "Copy message" }));
    await act(async () => void (await Promise.resolve()));
  };

  it("announces Copied., clears it after a few seconds so a repeat copy is announced", async () => {
    render(<TradeOutcome result={RESULT} give={["A"]} get={["B"]} />);
    await copy();
    expect(screen.getByRole("status")).toHaveTextContent("Copied.");
    act(() => void vi.advanceTimersByTime(COPIED_NOTE_MS + 10));
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it("resets the note when the message text changes", async () => {
    const { rerender } = render(<TradeOutcome result={RESULT} give={["A"]} get={["B"]} />);
    await copy();
    rerender(<TradeOutcome result={RESULT} give={["A", "C"]} get={["B"]} />);
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
  });

  it.each([[null, ["B"]], [["A"], null], [[], ["B"]]])("hides the message when a name list is missing (%j, %j)", (give, get) => {
    render(<TradeOutcome result={RESULT} give={give} get={get} />);
    expect(screen.queryByLabelText("Message to copy")).toBeNull();
    expect(screen.getByText(/names are not loaded/i)).toBeInTheDocument();
  });
});
