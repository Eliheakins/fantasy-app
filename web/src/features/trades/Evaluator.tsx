import { useId } from "react";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Section } from "@/components/Section";
import { useApi } from "@/hooks/useApi";
import { BUILDER_DEBOUNCE_MS } from "@/features/moves/builder";
import { TradeOutcome } from "@/features/moves/TradeOutcome";
import { useDebounced } from "@/features/moves/useDebounced";
import { FailureNotice } from "./FailureNotice";
import { canEvaluate, EMPTY_DRAFT, toRequest, tradeKey } from "./logic";
import { MultiSelect } from "./MultiSelect";
import type { Asset, Draft, Partner, TradeEvaluation } from "./types";
import { useKeptState } from "./useKeptState";
import { usePostApi } from "./usePostApi";

const toOptions = (assets: readonly Asset[]) => assets.map((a) => ({ id: a.gsis_id, label: a.label }));

/** `scope` (league plus viewed team) keys the kept draft; it defaults to the league. */
type EvaluatorProps = { league: string; scope?: string; partners: readonly Partner[]; mine: readonly Asset[]; debounceMs?: number };

const namesOf = (assets: readonly Asset[], ids: readonly string[]) =>
  ids.flatMap((id) => assets.find((a) => a.gsis_id === id)?.full_name ?? []);

/** The live trade builder: every change to either side re-evaluates once the picks settle for `debounceMs`. */
export function Evaluator({ league, scope = league, partners, mine, debounceMs = BUILDER_DEBOUNCE_MS }: EvaluatorProps) {
  const selectId = useId();
    const [stored, setDraft] = useKeptState<Draft>(["draft", scope], EMPTY_DRAFT);
  const partner = stored.partner !== null && partners.some((p) => p.roster_id === stored.partner)
    ? stored.partner
    : (partners[0]?.roster_id ?? null);
  const draft: Draft = { ...stored, partner };
  const partnerName = partners.find((p) => p.roster_id === partner)?.team_name ?? "";
  const theirs = useApi<Asset[]>(
    partner === null ? null : `/api/leagues/${encodeURIComponent(league)}/trade-assets?roster_id=${partner}`,
  );
  const settledKey = useDebounced(tradeKey(draft), debounceMs); // the key is a string, so the timer restarts only on a real change
  const [settledPartner, settledGive, settledGet] = JSON.parse(settledKey) as [number | null, string[], string[]];
  const settled: Draft = { partner: settledPartner, give: settledGive, get: settledGet };
  const active = toRequest(settled);
  const { state, refetch } = usePostApi<TradeEvaluation>(
    ["evaluate", scope, settledKey],
    `/api/leagues/${encodeURIComponent(league)}/trades/evaluate`,
    active,
  );

  return (
    <Section
      title="Build a trade"
      caption="Points are projected totals for the rest of the season. Each roster keeps its size: extra players are dropped and open spots filled with the best free agent. Odds assume current rosters."
    >
      <div className="space-y-3">
      <div>
        <label htmlFor={selectId} className="mb-1 block text-muted">Trade partner</label>
        <select
          id={selectId}
          value={partner ?? ""}
          onChange={(e) => setDraft({ partner: Number(e.target.value), give: draft.give, get: [] })}
          className="h-[44px] w-full max-w-sm rounded-full border border-panel-line bg-panel px-4"
        >
          {partners.map((p) => (
            <option key={p.roster_id} value={p.roster_id}>{p.team_name}</option>
          ))}
        </select>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <MultiSelect legend="I give (rest-of-season points)" options={toOptions(mine)} selected={draft.give} onChange={(give) => setDraft({ ...draft, give })} />
        <ApiBoundary state={theirs}>
          {(assets) => (
            <MultiSelect
              legend={`I get from ${partnerName} (rest-of-season points)`}
              options={toOptions(assets)}
              selected={draft.get}
              onChange={(get) => setDraft({ ...draft, get })}
            />
          )}
        </ApiBoundary>
      </div>
      {!canEvaluate(draft) && <p className="text-caption text-muted">Pick at least one player on each side.</p>}
      {state?.kind === "loading" && <p role="status" className="text-muted">Simulating the trade…</p>}
      {state?.kind === "error" && <FailureNotice error={state.error} onRetry={refetch} />}
      {state && state.kind !== "error" && state.kind !== "loading" && (
        <ApiBoundary state={state}>{(result) => <TradeOutcome result={result} give={namesOf(mine, settled.give)} get={namesOf(theirs.kind === "ready" ? theirs.data : [], settled.get)} />}</ApiBoundary>
      )}
      </div>
    </Section>
  );
}
