import { useEffect, useState } from "react";
import { possessive } from "@/lib/text";
import { points } from "@/features/trades/logic";
import { TradeResult } from "@/features/trades/TradeResult";
import type { TradeEvaluation } from "@/features/trades/types";
import { ExplainDelta, NOISE_PERCENT, NOISE_WINS } from "@/viz";
import { COPIED_NOTE_MS, canPitch, copyText, pitchText } from "./builder";

type Side = TradeEvaluation["odds"][number];

const sideWhy = (side: Side, what: string, wins = false) =>
  `${possessive(side.team_name)} ${what} after the trade minus before it, from the same simulated seasons run with and without the trade.${wins ? " Wins, not percentage points." : " Percentage points."}`;

function SideChange({ side }: { side: Side }) {
  return (
    <div className="min-w-0">
      <h3 className="font-semibold">{side.team_name}</h3>
      <p className="flex flex-wrap items-baseline gap-x-3">
        <span className="whitespace-nowrap"><ExplainDelta points={points(side.playoff_after - side.playoff_before)} noise={NOISE_PERCENT} why={sideWhy(side, "chance to make the playoffs")} /> <span className="text-caption text-muted">playoff pts</span></span>
        <span className="whitespace-nowrap"><ExplainDelta points={points(side.title_after - side.title_before)} noise={NOISE_PERCENT} why={sideWhy(side, "title chance")} /> <span className="text-caption text-muted">title pts</span></span>
        <span className="whitespace-nowrap"><ExplainDelta points={side.wins_after - side.wins_before} noise={NOISE_WINS} why={sideWhy(side, "expected wins", true)} /> <span className="text-caption text-muted">wins</span></span>
      </p>
    </div>
  );
}

function Pitch({ text }: { text: string }) {
  const [copied, setCopied] = useState<boolean | null>(null);
  useEffect(() => {
    if (copied === null) return;
    const timer = setTimeout(() => setCopied(null), COPIED_NOTE_MS);
    return () => clearTimeout(timer);
  }, [copied]);
  return (
    <div className="mt-4">
      <p className="mb-1 text-caption text-muted">This trade helps both teams. A message you can send, built from the numbers above; nothing is sent from here.</p>
      <textarea readOnly aria-label="Message to copy" value={text} rows={4} className="w-full rounded border border-line bg-page p-2" />
      <button
        type="button"
        onClick={() => void copyText(text).then(setCopied)}
        className="min-h-[44px] rounded bg-focus px-4 text-white"
      >
        Copy message
      </button>
      <span role="status" className="ml-3 text-caption text-muted">{copied === null ? "" : copied ? "Copied." : "Could not copy; select the text and copy it."}</span>
    </div>
  );
}

/** `give` and `get` are the players' names, or null when a name is not known yet (then no message is offered). */
type Props = { result: TradeEvaluation; give: readonly string[] | null; get: readonly string[] | null };

function PitchOrNote({ result, give, get }: Props) {
  if (!canPitch(result)) return <p className="text-caption text-muted">No message offered: the trade does not raise both teams' playoff odds.</p>;
  if (!give?.length || !get?.length) return <p className="text-caption text-muted">No message offered: the players' names are not loaded yet.</p>;
  const text = pitchText(result, give, get);
  return <Pitch key={text} text={text} />;
}

/** My change beside the partner's, the pitch when both gain, then the full before and after. */
export function TradeOutcome({ result, give, get }: Props) {
  const me = result.odds.find((s) => s.side === "me");
  const them = result.odds.find((s) => s.side === "them");
  return (
    <div className="space-y-4">
      {me && them && (
        <section aria-label="Both sides" className="grid gap-3 rounded-xl bg-panel p-4 md:grid-cols-2">
          <SideChange side={me} />
          <SideChange side={them} />
        </section>
      )}
      <PitchOrNote result={result} give={give} get={get} />
      <TradeResult result={result} />
    </div>
  );
}
