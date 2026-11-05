import { type ReactNode, useId } from "react";

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

/** An h2 section: heading, optional caption and method note, then the content. */
export function Section({ title, caption, howCalculated, children, level = 2 }: Props) {
  const id = useId();
  const Heading = level === 3 ? "h3" : "h2";
  return (
    <section aria-labelledby={id} className="mt-8 border-t border-line pt-6 first:mt-0 first:border-t-0 first:pt-0">
      <Heading id={id} className="text-heading font-semibold">{title}</Heading>
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
