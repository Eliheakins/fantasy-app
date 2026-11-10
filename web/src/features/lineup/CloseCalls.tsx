import { Confidence, Explain, formatPercent } from "@/viz";
import { slotShareWhy } from "./explain";
import { type SlotCall, REASON_OF, callText, scratchFallbacks, splitCalls, winnerShare } from "./calls";
import { type LineupRow, type ObjectiveKey, slotLabel } from "./logic";

const LIST_ITEM = "flex min-h-[44px] flex-wrap items-center gap-x-3 border-b border-line py-2 last:border-b-0";

/** The slots that are genuinely close, then what to do if a starter is scratched. */
export function CloseCalls({
  calls,
  rows,
  objective,
}: {
  calls: readonly SlotCall[];
  rows: readonly LineupRow[];
  objective: ObjectiveKey;
}) {
  const names = Object.fromEntries(rows.map((r) => [r.gsis_id, r.full_name]));
  const locked = new Set(rows.filter((r) => r.locked).map((r) => r.gsis_id));
  const { close, clear } = splitCalls(calls, locked);
  const reason = REASON_OF[objective];
  const fallbacks = scratchFallbacks(rows);
  const open = close.length + clear.length;
  if (open === 0 && fallbacks.length === 0) return null;
  return (
    <section aria-labelledby="close-calls" className="mt-10">
      <h2 id="close-calls" className="text-section font-semibold">
        Close calls
      </h2>
      {open > 0 && close.length === 0 && <p className="mt-2 text-body">No slot is close.</p>}
      {close.length > 0 && (
        <ul className="mt-2">
          {close.map((c) => (
            <li key={`${c.slot}|${c.starter}`} className={LIST_ITEM}>
              <span>{callText(c, names, reason)}</span>
              {c.share !== null && (
                <Explain
                  why={slotShareWhy(c.share)}
                  about={`${slotLabel(c.slot)}, starter ahead in ${formatPercent(c.share)} of paired draws`}
                >
                  <Confidence share={winnerShare(c)} />
                </Explain>
              )}
            </li>
          ))}
        </ul>
      )}
      {clear.length > 0 && (
        <details className="mt-1 text-body">
          <summary className="flex min-h-[44px] cursor-pointer items-center text-forest">
            {clear.length} {clear.length === 1 ? "slot is" : "slots are"} clear
          </summary>
          <ul>
            {clear.map((c) => (
              <li key={`${c.slot}|${c.starter}`} className="py-1 text-caption text-muted">
                {callText(c, names)}
              </li>
            ))}
          </ul>
        </details>
      )}
      {fallbacks.length > 0 && (
        <>
          <h3 className="mt-3 text-body font-semibold">If a starter is scratched</h3>
          <ul>
            {fallbacks.map((f) => (
              <li key={f.gsisId} className={LIST_ITEM}>
                {f.text}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
