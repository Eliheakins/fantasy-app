import { ApiBoundary } from "@/components/ApiBoundary";
import { Section } from "@/components/Section";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { Delta, NOISE_PERCENT } from "@/viz";
import { FailureNotice } from "./FailureNotice";
import { marketDate, marketText, points } from "./logic";
import type { FoundTrade } from "./types";
import { useKeptState } from "./useKeptState";
import { usePostApi } from "./usePostApi";

/** "You fill: WR" / "They fill: RB, WR" on two lines; a side with no named need says "none". */
export function FillsNote({ r }: { r: Pick<FoundTrade, "my_fills" | "their_fills"> }) {
  return (
    <>
      <span className="block whitespace-nowrap">{`You fill: ${r.my_fills || "none"}`}</span>
      <span className="block whitespace-nowrap">{`They fill: ${r.their_fills || "none"}`}</span>
    </>
  );
}

/** The partner and the kind of trade; "need swap" says what that means because it is not a win for both. */
function PartnerKind({ r }: { r: FoundTrade }) {
  const kind = r.kind.replace("-", "\u2011"); // no line break inside "win-win"
  return (
    <>
      {r.partner}
      <span className="block whitespace-nowrap text-caption font-normal text-muted">
        {kind}
      </span>
    </>
  );
}

const odds = (fraction: number) => <Delta points={points(fraction)} noise={NOISE_PERCENT} />;

const COLUMNS: readonly Column<FoundTrade>[] = [
  { label: "Partner", role: "primary", render: (r) => <PartnerKind r={r} /> },
  { label: "You give", render: (r) => r.give },
  { label: "You get", render: (r) => r.get },
  { label: "Your playoff odds (pp)", numeric: true, render: (r) => odds(r.my_playoff) },
  { label: "Your title odds (pp)", numeric: true, render: (r) => odds(r.my_title) },
  { label: "Their playoff odds (pp)", numeric: true, render: (r) => odds(r.their_playoff) },
  { label: "Their title odds (pp)", numeric: true, render: (r) => odds(r.their_title) },
  { label: "Needs filled", render: (r) => <FillsNote r={r} /> },
  {
    label: "Market value",
    role: "detail",
    render: (r) =>
      r.market ? (
        <span className="text-muted">
          {`${marketText(r.market)} `}
          <span className="whitespace-nowrap">{`(${marketDate(r.market)})`}</span>
        </span>
      ) : (
        ""
      ),
  },
  { label: "Title error (\u00b1 pp)", role: "detail", numeric: true, render: (r) => points(r.se_title).toFixed(2) },
];

export function FoundTradesTable({ rows }: { rows: readonly FoundTrade[] }) {
  if (rows.length === 0) {
    return <p className="measure py-2 text-muted">No trade fills a need for both teams right now. Try again after rosters or waivers change.</p>;
  }
  return (
    <ResponsiveTable
      caption="Trades that fill a position of need for both teams, with the change in odds in percentage points"
      columns={COLUMNS}
      breakpoint="xl"
      rows={rows}
      rowKey={(r) => `${r.partner}|${r.give}|${r.get}`}
    />
  );
}

function HowToRead() {
  return (
    <details className="measure mt-2 text-caption text-muted">
      <summary className="flex min-h-[44px] cursor-pointer items-center">How to read this</summary>
      <div className="space-y-2 pb-2">
        <p>
          Trades are one or two players each way, using players the other side can spare, best need fit first.
          pp is percentage points: +1.2 means the chance went from, say, 40.0% to 41.2%.
        </p>
        <p>
          "win-win" raises both teams' playoff plus title odds. "need swap" costs a side up to one point of those
          odds for a need filled, so one side may give up a little to fix a hole.
        </p>
        <p>
          A side left with an open roster spot is compared with itself after its own best waiver move. The
          title odds error is the simulation error of the title change.
        </p>
        <p>
          Market value sums FantasyCalc values for each side and says only which side the market favors. It
          ignores the premium paid to turn two players into one. Managers accept trades based on how they value
          players, which is not modeled, so nothing here says a partner will accept.
        </p>
      </div>
    </details>
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
    <Section
      title="Find trades"
      caption="Looks for trades of one or two players each way that fill a position where each team is thin. A run takes up to a minute and the result is kept if you leave this page."
    >
      <div className="space-y-3">
      <button
        type="button"
        disabled={running}
        aria-busy={running}
        onClick={() => (requested ? refetch() : setRequested(true))}
        className="min-h-[44px] rounded bg-accent px-4 text-accent-fg"
      >
        {running ? "Searching…" : state?.kind === "ready" ? "Find trades again" : "Find trades"}
      </button>
      {state?.kind === "error" ? (
        <FailureNotice error={state.error} onRetry={refetch} />
      ) : state ? (
        <ApiBoundary state={state}>{(rows) => <FoundTradesTable rows={rows} />}</ApiBoundary>
      ) : null}
      <HowToRead />
      </div>
    </Section>
  );
}
