import { type ReactNode, useId } from "react";

type Props = {
  title: string;
  /** One or two lines under the heading, capped at the reading measure. */
  caption?: ReactNode;
  /** Longer method text, folded under a 44 px "How this is calculated" disclosure. */
  howCalculated?: ReactNode;
  children: ReactNode;
};

/** An h2 section: heading, optional caption and method note, then the content. */
export function Section({ title, caption, howCalculated, children }: Props) {
  const id = useId();
  return (
    <section aria-labelledby={id} className="mt-8 first:mt-0">
      <h2 id={id} className="text-heading font-semibold">{title}</h2>
      {caption && <p className="measure mt-1 text-caption text-muted">{caption}</p>}
      {howCalculated && (
        <details className="measure mt-1 text-caption text-muted">
          <summary className="flex min-h-[44px] cursor-pointer items-center">How this is calculated</summary>
          <div className="pb-2">{howCalculated}</div>
        </details>
      )}
      <div className="mt-2">{children}</div>
    </section>
  );
}
