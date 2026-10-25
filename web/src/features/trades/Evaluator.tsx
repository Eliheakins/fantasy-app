import { useId } from "react";
import { ApiBoundary } from "@/components/ApiBoundary";
import { useApi } from "@/hooks/useApi";
import { FailureNotice } from "./FailureNotice";
import { canEvaluate, EMPTY_DRAFT, toRequest, tradeKey } from "./logic";
import { MultiSelect } from "./MultiSelect";
import { TradeResult } from "./TradeResult";
import type { Asset, Draft, Partner, TradeEvaluation } from "./types";
import { useKeptState } from "./useKeptState";
import { usePostApi } from "./usePostApi";

const toOptions = (assets: readonly Asset[]) => assets.map((a) => ({ id: a.gsis_id, label: a.label }));

/** `scope` (league plus viewed team) keys the kept draft; it defaults to the league. */
type EvaluatorProps = { league: string; scope?: string; partners: readonly Partner[]; mine: readonly Asset[] };

export function Evaluator({ league, scope = league, partners, mine }: EvaluatorProps) {
  const selectId = useId();
  const [stored, setDraft] = useKeptState<Draft>(["draft", scope], EMPTY_DRAFT);
  const [submitted, setSubmitted] = useKeptState<Draft | null>(["submitted", scope], null);
  const partner = stored.partner !== null && partners.some((p) => p.roster_id === stored.partner)
    ? stored.partner
    : (partners[0]?.roster_id ?? null);
  const draft: Draft = { ...stored, partner };
  const partnerName = partners.find((p) => p.roster_id === partner)?.team_name ?? "";
  const theirs = useApi<Asset[]>(
    partner === null ? null : `/api/leagues/${encodeURIComponent(league)}/trade-assets?roster_id=${partner}`,
  );
  const active = submitted !== null && tradeKey(submitted) === tradeKey(draft) ? toRequest(draft) : null;
  const { state, refetch } = usePostApi<TradeEvaluation>(
    ["evaluate", scope, tradeKey(draft)],
    `/api/leagues/${encodeURIComponent(league)}/trades/evaluate`,
    active,
  );

  return (
    <section aria-labelledby="eval-h" className="space-y-3">
      <h2 id="eval-h" className="text-body font-semibold">Evaluate a trade</h2>
      <div>
        <label htmlFor={selectId} className="mb-1 block text-muted">Trade partner</label>
        <select
          id={selectId}
          value={partner ?? ""}
          onChange={(e) => setDraft({ partner: Number(e.target.value), give: draft.give, get: [] })}
          className="h-[44px] w-full max-w-sm rounded border border-border bg-page px-2"
        >
          {partners.map((p) => (
            <option key={p.roster_id} value={p.roster_id}>{p.team_name}</option>
          ))}
        </select>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <MultiSelect legend="I give" options={toOptions(mine)} selected={draft.give} onChange={(give) => setDraft({ ...draft, give })} />
        <ApiBoundary state={theirs}>
          {(assets) => (
            <MultiSelect
              legend={`I get from ${partnerName}`}
              options={toOptions(assets)}
              selected={draft.get}
              onChange={(get) => setDraft({ ...draft, get })}
            />
          )}
        </ApiBoundary>
      </div>
      <p className="text-caption text-muted">
        Points are projected totals for the rest of the season. Each roster keeps its size: extra players are
        dropped and open spots filled with the best free agent. Odds assume current rosters.
      </p>
      <button
        type="button"
        disabled={!canEvaluate(draft) || state?.kind === "loading" || state?.kind === "running"}
        onClick={() => setSubmitted(draft)}
        className="min-h-[44px] rounded bg-accent px-4 text-accent-fg disabled:opacity-50"
      >
        Evaluate
      </button>
      {!canEvaluate(draft) && <p className="text-caption text-muted">Pick at least one player on each side.</p>}
      {state?.kind === "loading" && <p role="status" className="text-muted">Simulating the trade…</p>}
      {state?.kind === "error" && <FailureNotice error={state.error} onRetry={refetch} />}
      {state && state.kind !== "error" && state.kind !== "loading" && (
        <ApiBoundary state={state}>{(result) => <TradeResult result={result} />}</ApiBoundary>
      )}
    </section>
  );
}
