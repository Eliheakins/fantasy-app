import { type ReactNode, useId, useState } from "react";

type Props = {
  title: string;
  /** One or two lines under the heading, capped at the reading measure. */
  caption?: ReactNode;
  /** Longer method text, folded under a 44 px "How this is calculated" disclosure. */
  howCalculated?: ReactNode;
  children: ReactNode;
  /** Heading level; 3 where the section sits under an h2 (a compare column). */
  level?: 2 | 3;
};

/** An h2 section: heading with an optional "How this is calculated" link on the same row, caption, then the content. */
export function Section({ title, caption, howCalculated, children, level = 2 }: Props) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const Heading = level === 3 ? "h3" : "h2";
  return (
    <section aria-labelledby={id} className="mt-10 border-t border-line pt-6 first:mt-0 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        <Heading id={id} className={level === 3 ? "text-heading font-semibold" : "text-section font-semibold"}>{title}</Heading>
        {howCalculated && (
          <button
            type="button"
            aria-expanded={open}
            aria-controls={open ? `${id}-method` : undefined}
            onClick={() => setOpen((o) => !o)}
            className="-my-3 inline-flex min-h-[44px] items-center text-caption text-focus underline underline-offset-2 hover:text-forest"
          >
            How this is calculated
          </button>
        )}
      </div>
      {caption && <p className="measure mt-1 text-caption text-muted">{caption}</p>}
      {howCalculated && open && <div id={`${id}-method`} className="measure mt-2 rounded-lg border border-line p-3 text-caption text-muted">{howCalculated}</div>}
      <div className="mt-3">{children}</div>
    </section>
  );
}
