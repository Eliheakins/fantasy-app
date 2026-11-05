import {
  QueryBuilderSidebarExecuteFooter,
  QueryBuilderSidebarScroll,
  type QueryBuilderSidebarScrollProps,
} from "@/features/explore/QueryBuilderSidebarBody";
import { Button } from "@/shared/components/ui/button";
import { cn } from "@/shared/lib/utils";
import { Drawer } from "vaul";

/** Mobile sheet: full viewport height only (Vaul fractions 0–1, not 0–100). */
const MOBILE_BUILDER_SNAP_POINTS: (number | string)[] = [1];

export interface ExploreMobileBuilderDrawerProps {
  sidebarScrollProps: QueryBuilderSidebarScrollProps;
  running: boolean;
  onExecute: () => void;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  activeSnapPoint: number | string | null;
  onActiveSnapChange: (v: number | string | null) => void;
}

export function ExploreMobileBuilderDrawer({
  sidebarScrollProps,
  running,
  onExecute,
  open,
  onOpenChange,
  activeSnapPoint,
  onActiveSnapChange,
}: ExploreMobileBuilderDrawerProps) {
  return (
    <>
      <button
        type="button"
        onClick={() => {
          onActiveSnapChange(1);
          onOpenChange(true);
        }}
        className={cn(
          "fixed z-[70] flex h-14 w-14 items-center justify-center rounded-full bg-primary text-surface shadow-lg lg:hidden",
          "transition hover:brightness-110 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2 focus-visible:ring-offset-app",
          "bottom-[max(1.25rem,env(safe-area-inset-bottom,0px))] right-4",
          open && "hidden",
        )}
        aria-label="Open query builder"
        aria-expanded={open}
        aria-haspopup="dialog"
        tabIndex={open ? -1 : undefined}
      >
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <path d="M3 6h18M7 12h10M11 18h2" strokeLinecap="round" />
        </svg>
      </button>

      <Drawer.Root
        open={open}
        onOpenChange={(next) => {
          onOpenChange(next);
          onActiveSnapChange(1);
        }}
        snapPoints={MOBILE_BUILDER_SNAP_POINTS}
        activeSnapPoint={activeSnapPoint}
        setActiveSnapPoint={onActiveSnapChange}
        modal
        shouldScaleBackground={false}
        dismissible
        noBodyStyles
        autoFocus
      >
        <Drawer.Portal>
          <Drawer.Overlay className="fixed inset-0 z-[65] bg-ink/40 backdrop-blur-[1px]" />
          <Drawer.Content
            className={cn(
              "fixed inset-x-0 bottom-0 z-[66] flex max-h-[100dvh] flex-col rounded-t-2xl border-x border-t border-border bg-surface shadow-[0_-8px_30px_rgb(15_23_42/0.12)] outline-none",
            )}
          >
            <div className="relative flex shrink-0 flex-col items-center pt-2">
              <Drawer.Close asChild>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="absolute right-2 top-1 z-10 h-10 w-10 shrink-0 rounded-full p-0 text-ink hover:bg-input"
                  aria-label="Close query builder"
                >
                  <svg
                    width="20"
                    height="20"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    aria-hidden
                  >
                    <path d="M18 6L6 18M6 6l12 12" strokeLinecap="round" />
                  </svg>
                </Button>
              </Drawer.Close>
              <Drawer.Handle className="mx-auto mb-2 mt-1 h-1.5 w-12 shrink-0 rounded-full bg-border" />
            </div>
            <Drawer.Title className="sr-only">Query builder</Drawer.Title>
            <Drawer.Description className="sr-only">
              Adjust players, metrics, aggregation, and context filters. Results update in the view above.
            </Drawer.Description>
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
              <div className="min-h-0 flex-1 overflow-y-auto px-4">
                <div className="flex flex-col gap-5 pb-2 pt-1">
                  <QueryBuilderSidebarScroll {...sidebarScrollProps} />
                </div>
              </div>
              <QueryBuilderSidebarExecuteFooter
                running={running}
                onExecute={onExecute}
                className="rounded-none border-t border-border p-3 pt-2"
              />
            </div>
          </Drawer.Content>
        </Drawer.Portal>
      </Drawer.Root>
    </>
  );
}
