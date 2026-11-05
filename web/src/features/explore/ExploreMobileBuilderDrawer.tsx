import { SlidersHorizontal, X } from "lucide-react";
import { Dialog } from "radix-ui";
import { useState } from "react";
import {
  QueryBuilderSidebarExecuteFooter,
  QueryBuilderSidebarScroll,
  type QueryBuilderSidebarScrollProps,
} from "@/features/explore/QueryBuilderSidebarBody";

export interface ExploreMobileBuilderDrawerProps {
  sidebarScrollProps: QueryBuilderSidebarScrollProps;
  running: boolean;
  onExecute: () => void;
}

/** Phone builder: a full-height Radix Dialog sheet (focus trap, Esc, labelled) opened from a floating button. */
export function ExploreMobileBuilderDrawer({ sidebarScrollProps, running, onExecute }: ExploreMobileBuilderDrawerProps) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      {/* In the page flow, not floating, so it never covers table cells. */}
      <Dialog.Trigger className="flex min-h-11 w-full items-center justify-center gap-2 rounded-md border border-border bg-surface text-body font-medium text-text lg:hidden">
        <SlidersHorizontal size={18} aria-hidden />
        Open query builder
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-page/70" />
        <Dialog.Content className="fixed inset-x-0 bottom-0 z-50 flex max-h-dvh flex-col rounded-t-2xl border-x border-t border-border bg-surface outline-hidden">
          <div className="flex shrink-0 items-center justify-between px-4 pt-2">
            <Dialog.Title className="text-heading font-semibold">Query builder</Dialog.Title>
            <Dialog.Close aria-label="Close query builder" className="flex h-11 w-11 items-center justify-center rounded-full text-text">
              <X size={20} aria-hidden />
            </Dialog.Close>
          </div>
          <Dialog.Description className="sr-only">
            Adjust players, metrics, aggregation, and context filters. Execute analysis closes this sheet and shows the results.
          </Dialog.Description>
          <div className="min-h-0 flex-1 overflow-y-auto px-4">
            <div className="flex flex-col gap-5 pb-2 pt-1">
              <QueryBuilderSidebarScroll {...sidebarScrollProps} />
            </div>
          </div>
          <QueryBuilderSidebarExecuteFooter running={running}
            onExecute={() => {
              setOpen(false);
              onExecute();
            }} className="border-t border-border p-3 pt-2" />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
