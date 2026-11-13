import type { ApiState } from "@/api/envelope";
import { ApiBoundary } from "@/components/ApiBoundary";
import { Callout } from "@/components/Callout";
import { PlayerLink } from "@/components/PlayerLink";
import { type Column, ResponsiveTable } from "@/components/ResponsiveTable";
import { Section } from "@/components/Section";
import { formatNumber } from "@/viz";
import { STASH_ANCHOR, STASH_CAPTION, type StashData, type StashRow } from "./logic";
import { linkButtonClass } from "@/components/ui/styles";
import { cn } from "@/lib/utils";

const COLUMNS: Column<StashRow>[] = [
  {
    label: "Player",
    role: "primary",
    render: (r) => (
      <>
        <PlayerLink gsisId={r.gsis_id} name={r.full_name} position={r.position} />{" "}
        <span className="text-caption font-normal text-muted">{r.position}</span>
      </>
    ),
  },
  { label: "Status", render: (r) => r.status },
  { label: "First projected week", numeric: true, render: (r) => (r.first_week == null ? "–" : String(r.first_week)) },
  { label: "Playoff weeks (pts)", numeric: true, render: (r) => formatNumber(r.playoff_points) },
  { label: "Owner", render: (r) => (r.is_mine ? "Yours" : "Free agent") },
  { label: "IR-eligible", render: (r) => (r.ir_eligible ? "Yes" : "No") },
];

/** An open IR slot and an injured player who may fill it: a note, not an alert. */
export function OpenIrCallout({ data }: { data: StashData }) {
  if (data.open_ir_slots <= 0 || !data.rows.some((r) => r.ir_eligible)) return null;
  const slots = data.open_ir_slots;
  return (
    <aside aria-label="Open IR slot" className="mb-4">
      <Callout variant="info">
        You have {slots} open IR {slots === 1 ? "slot" : "slots"}.{" "}
        <a href={`#${STASH_ANCHOR}`} className={cn(linkButtonClass, "underline-offset-2 lg:min-h-0")}>
          See injured players to stash
        </a>
        .
      </Callout>
    </aside>
  );
}

export function StashSection({ state }: { state: ApiState<StashData> }) {
  return (
    <div id={STASH_ANCHOR}>
      <Section title="Stash for playoffs" caption={STASH_CAPTION}>
        <ApiBoundary state={state}>
          {(data) =>
            data.rows.length === 0 ? (
              <p className="py-6 text-muted">No injured players worth stashing</p>
            ) : (
              <ResponsiveTable
                caption="Injured players to stash"
                columns={COLUMNS}
                rows={data.rows}
                rowKey={(r) => r.gsis_id}
                isStrong={(r) => r.is_mine}
              />
            )
          }
        </ApiBoundary>
      </Section>
    </div>
  );
}
