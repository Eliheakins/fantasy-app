import { ApiBoundary } from "@/components/ApiBoundary";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { Delta, NOISE_PERCENT } from "@/viz";
import { FailureNotice } from "./FailureNotice";
import { marketDate, marketText, points } from "./logic";
import type { FoundTrade } from "./types";
import { useKeptState } from "./useKeptState";
import { usePostApi } from "./usePostApi";

/** "fills WR, they fill RB"; a side with no named need says so plainly. */
export function needNote(r: Pick<FoundTrade, "my_fills" | "their_fills">): string {
  const mine = r.my_fills ? `fills ${r.my_fills}` : "fills no need";
  const theirs = r.their_fills ? `they fill ${r.their_fills}` : "they fill no need";
  return `${mine}, ${theirs}`;
}

const COLUMNS: readonly Column<FoundTrade>[] = [
  { label: "Partner", render: (r) => r.partner },
  { label: "You give", render: (r) => r.give },
  { label: "You get", render: (r) => r.get },
  { label: "Needs", render: needNote },
  { label: "Kind", render: (r) => r.kind },
  {
    label: "Market value",
    render: (r) =>
      r.market ? <span className="text-muted">{`${marketText(r.market)} (${marketDate(r.market)})`}</span> : "",
  },
  { label: "Your playoffs (pts)", render: (r) => <Delta points={points(r.my_playoff)} noise={NOISE_PERCENT} /> },
  { label: "Your title (pts)", render: (r) => <Delta points={points(r.my_title)} noise={NOISE_PERCENT} /> },
  { label: "Their playoffs (pts)", render: (r) => <Delta points={points(r.their_playoff)} noise={NOISE_PERCENT} /> },
  { label: "Their title (pts)", render: (r) => <Delta points={points(r.their_title)} noise={NOISE_PERCENT} /> },
  { label: "Error (pts)", render: (r) => `${points(r.se_title).toFixed(2)}%` },
];

export function FoundTradesTable({ rows }: { rows: readonly FoundTrade[] }) {
  if (rows.length === 0) return <p className="py-2">No trade fills a need for both teams right now.</p>;
  return (
    <ResponsiveTable
      caption="Trades that fill a position of need for both teams, with the change in odds in percentage points"
      columns={COLUMNS}
      rows={rows}
      rowKey={(r) => `${r.partner}|${r.give}|${r.get}`}
    />
  );
}

export function FindTradesSection({ league, scope = league }: { league: string; scope?: string }) {
  const [requested, setRequested] = useKeptState<boolean>(["finder-requested", scope], false);
  const { state, refetch } = usePostApi<FoundTrade[]>(
    ["find-trades", scope],
    `/api/leagues/${encodeURIComponent(league)}/trades/find`,
    requested ? {} : null,
  );
  const running = state?.kind === "running" || (requested && state?.kind === "loading");
  return (
    <section aria-labelledby="find-h" className="space-y-2">
      <h2 id="find-h" className="text-body font-semibold">Find trades</h2>
      <p className="text-caption text-muted">
        Trades of one or two players each way (1 for 1, 1 for 2, 2 for 1, 2 for 2) that fill a position where each
        team is thin, using players the other side can spare, best need fit first. "win-win" raises both teams'
        playoff plus title odds. "need swap" costs a side up to one point of those odds for a need filled, so
        one side may give up a little to fix a hole. Managers accept trades based on how they value players,
        which is not modeled, so nothing here says a partner will accept. A side left with an open roster spot
        is compared with itself after its own best waiver move. Changes are in percentage points; error is the
        Monte Carlo error of your title change. Market value sums FantasyCalc values for each side and says only
        which side the market favors; it ignores the premium paid to turn two players into one. Searching can take several minutes; the result is kept if you
        leave this page.
      </p>
      <button
        type="button"
        disabled={running}
        onClick={() => (requested ? refetch() : setRequested(true))}
        className="min-h-[44px] rounded bg-accent px-4 text-accent-fg disabled:opacity-50"
      >
        {state?.kind === "ready" ? "Find trades again" : "Find trades"}
      </button>
      {state?.kind === "error" ? (
        <FailureNotice error={state.error} onRetry={refetch} />
      ) : state ? (
        <ApiBoundary state={state}>{(rows) => <FoundTradesTable rows={rows} />}</ApiBoundary>
      ) : null}
    </section>
  );
}
