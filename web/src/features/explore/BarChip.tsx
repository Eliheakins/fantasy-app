import type { ReactNode } from "react";

import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

const CHIP_CLASS =
  "inline-flex min-h-11 items-center gap-2 rounded-full border bg-surface px-3.5 text-body font-medium text-ink md:min-h-10 " +
  "hover:border-focus data-[state=open]:border-focus data-[state=open]:bg-panel";

function Caret() {
  return <span aria-hidden className="h-0 w-0 border-x-4 border-t-[5px] border-x-transparent border-t-muted" />;
}

/** A chip of the query bar: its label, and a popover with the controls for it. */
export function BarChip({
  label,
  ariaLabel,
  children,
  className,
}: {
  label: ReactNode;
  ariaLabel: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" aria-label={ariaLabel} className={cn(CHIP_CLASS, "border-panel-line", className)}>
          {label}
          <Caret />
        </button>
      </PopoverTrigger>
      <PopoverContent>{children}</PopoverContent>
    </Popover>
  );
}

/** A chip that holds one choice and can be removed (a stat, a pinned player, an active filter). */
export function RemovableChip({ label, removeLabel, onRemove }: { label: ReactNode; removeLabel: string; onRemove: () => void }) {
  return (
    <span className="inline-flex min-h-11 items-center overflow-hidden rounded-full border border-focus bg-panel text-body font-semibold text-forest md:min-h-10">
      <span className="pl-3.5 pr-1">{label}</span>
      <button
        type="button"
        aria-label={removeLabel}
        onClick={onRemove}
        className="flex h-11 w-10 items-center justify-center text-heading leading-none hover:bg-panel-line md:h-10"
      >
        <span aria-hidden>×</span>
      </button>
    </span>
  );
}

/** The dashed chip that adds something: "+ stat", "+ filter". */
export function AddChipTrigger({ label, ariaLabel, children }: { label: string; ariaLabel: string; children: ReactNode }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={ariaLabel}
          className="inline-flex min-h-11 items-center rounded-full border border-dashed border-focus bg-surface px-3.5 text-body font-semibold text-focus hover:bg-panel md:min-h-10"
        >
          {label}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[min(28rem,calc(100vw-1.5rem))]">{children}</PopoverContent>
    </Popover>
  );
}
