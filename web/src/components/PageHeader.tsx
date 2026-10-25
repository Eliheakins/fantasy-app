import type { ReactNode } from "react";

export const PAGE_HEADING_ID = "page-heading";

type Props = { title: string; subtitle?: ReactNode; actions?: ReactNode };

/** The page's one h1, with the same weight, size and spacing everywhere. Focus lands here on navigation. */
export function PageHeader({ title, subtitle, actions }: Props) {
  return (
    <div className="mb-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 id={PAGE_HEADING_ID} tabIndex={-1} className="text-title font-semibold outline-none">
          {title}
        </h1>
        {actions}
      </div>
      {subtitle && <p className="measure mt-1 text-caption text-muted">{subtitle}</p>}
    </div>
  );
}
