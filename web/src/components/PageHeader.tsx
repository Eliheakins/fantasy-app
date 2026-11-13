import type { ReactNode } from "react";
import { eyebrowClass } from "@/components/ui/styles";
import { cn } from "@/lib/utils";

export const PAGE_HEADING_ID = "page-heading";

type Props = {
  /** Text, or text with an inline Explain for the page's key number. */
  title: ReactNode;
  /** Forest-toned caps line above the h1: "page · week · context". */
  eyebrow?: string;
  /** One sentence under the h1 with the key number and its effect. */
  answer?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
};

/** The page's one h1, with the same weight, size and spacing everywhere. Focus lands here on navigation. */
export function PageHeader({ title, eyebrow, answer, subtitle, actions }: Props) {
  return (
    <div className="mb-8">
      {eyebrow && <p className={cn("mb-1", eyebrowClass)}>{eyebrow}</p>}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 id={PAGE_HEADING_ID} tabIndex={-1} className="text-h1 font-semibold text-ink outline-none">
          {title}
        </h1>
        {actions}
      </div>
      {answer && <p className="measure mt-2 text-[17px] leading-7 text-label">{answer}</p>}
      {subtitle && <p className="measure mt-1 text-caption text-muted">{subtitle}</p>}
    </div>
  );
}
