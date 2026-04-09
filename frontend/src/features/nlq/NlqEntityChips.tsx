import type { UnifiedNlqEntity } from "@/shared/lib/nlqApi";

function unifiedEntityKey(e: UnifiedNlqEntity, index: number): string {
  if (e.bridge_id != null && Number.isFinite(e.bridge_id)) {
    return `bridge-${e.bridge_id}`;
  }
  const parts = [e.display_name, e.nfl_gsis_id ?? "", e.cfb_espn_id ?? ""].join("|");
  return parts || `idx-${index}`;
}

export interface NlqEntityChipsProps {
  entities: UnifiedNlqEntity[];
}

export function NlqEntityChips({ entities }: NlqEntityChipsProps) {
  if (entities.length === 0) {
    return null;
  }
  return (
    <div>
      <p className="mb-1 text-xs font-medium uppercase tracking-wide text-ink-muted">Matched players</p>
      <ul className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        {entities.map((e, i) => (
          <li
            key={unifiedEntityKey(e, i)}
            className="min-w-0 rounded-md border border-border bg-input/60 px-2 py-1.5 text-xs text-ink"
          >
            <div className="font-medium leading-tight">{e.display_name}</div>
            <div className="mt-1 flex flex-wrap gap-x-2 gap-y-0.5 font-mono text-[10px] text-ink-muted">
              {e.bridge_id != null && Number.isFinite(e.bridge_id) && <span>bridge #{e.bridge_id}</span>}
              {e.nfl_gsis_id ? <span title="NFL GSIS">NFL {e.nfl_gsis_id}</span> : null}
              {e.cfb_espn_id ? <span title="CFB ESPN athlete id">CFB {e.cfb_espn_id}</span> : null}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
