import { Popover } from "radix-ui";
import { type ComponentProps, type ReactNode, useId, useRef } from "react";
import { cn } from "@/lib/utils";
import { Delta } from "./Delta";

const FOCUS = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#1F5A43]";
/** In a sentence the line height stays normal; an invisible pad makes the 44px hit area. */
const INLINE = "relative after:absolute after:-inset-x-1 after:-inset-y-3 after:content-['']";
/** A row-level number is its own 44px target. */
const ROW = "inline-flex min-h-[44px] items-center";

type ExplainProps = {
  why: ReactNode;
  children: ReactNode;
  /** What the number is about, added to the accessible name (for a bare word like "lean"). */
  about?: string;
  /** Row-level trigger: a 44px tall target instead of an inline one. */
  row?: boolean;
  /** Inside a heading: the "what drives this" hint becomes a description, not part of the heading's name. */
  inHeading?: boolean;
};

/** A key number that explains itself on click or Enter: what drives it, from data already on the page. Esc closes and focus returns to the number. */
export function Explain({ why, children, about, row = false, inHeading = false }: ExplainProps) {
  const trigger = useRef<HTMLButtonElement>(null);
  const hintId = useId();
  const hint = `${about ? `, ${about}` : ""}, what drives this`;
  return (
    <Popover.Root>
      {/* in a heading the hint is a description, so the heading's name stays its visible text */}
      {inHeading && <span id={hintId} hidden>{hint}</span>}
      <Popover.Trigger ref={trigger} aria-describedby={inHeading ? hintId : undefined} className={cn("rounded text-left underline decoration-dotted underline-offset-4", row ? ROW : INLINE, FOCUS)}>
        {children}
        {!inHeading && <span className="sr-only">{hint}</span>}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          sideOffset={4}
          collisionPadding={8}
          aria-label="What drives this number"
          onCloseAutoFocus={(e) => {
            if (!trigger.current?.isConnected) return;
            e.preventDefault();
            trigger.current.focus();
          }}
          className="z-50 max-w-[min(20rem,calc(100vw-16px))] rounded-md border border-line bg-surface px-3 py-2 text-caption leading-relaxed text-ink shadow-sm"
        >
          {why}
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}

type ExplainDeltaProps = ComponentProps<typeof Delta> & Pick<ExplainProps, "why" | "about" | "row"> & { children?: ReactNode };

/** A Delta whose sign and arrow are the button's label; `children` (a unit label) sit after the button, outside it. */
export function ExplainDelta({ why, about, row, children, ...delta }: ExplainDeltaProps) {
  return (
    <>
      <Explain why={why} about={about} row={row}><Delta {...delta} /></Explain>
      {children}
    </>
  );
}
