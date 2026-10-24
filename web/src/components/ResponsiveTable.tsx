import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export type Column<T> = { label: string; render: (row: T) => ReactNode; numeric?: boolean };

type Props<T> = {
  caption: string;
  columns: readonly Column<T>[];
  rows: readonly T[];
  rowKey: (row: T, index: number) => string;
  /** Emphasised row (my team); the caller also puts a text marker in a cell. */
  isStrong?: (row: T) => boolean;
};

/** A table at 768 px and up; stacked cards on a phone, each cell carrying its own label. */
export function ResponsiveTable<T>({ caption, columns, rows, rowKey, isStrong }: Props<T>) {
  return (
    <table className="w-full text-body">
      <caption className="sr-only">{caption}</caption>
      <thead className="max-md:sr-only">
        <tr className="border-b border-border text-left text-caption text-muted">
          {columns.map((c) => (
            <th key={c.label} scope="col" className={cn("px-2 py-1 font-normal", c.numeric && "text-right")}>
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody className="max-md:block">
        {rows.map((row, i) => (
          <tr
            key={rowKey(row, i)}
            className={cn(
              "border-b border-border max-md:mb-2 max-md:block max-md:rounded max-md:border max-md:p-2",
              isStrong?.(row) && "font-semibold md:border-l-4 md:border-l-accent max-md:border-l-4 max-md:border-l-accent",
            )}
          >
            {columns.map((c) => (
              <td
                key={c.label}
                className={cn("px-2 py-1 align-top max-md:flex max-md:min-h-[44px] max-md:items-center max-md:justify-between max-md:gap-3", c.numeric && "tabular-nums md:text-right")}
              >
                <span aria-hidden className="text-caption font-normal text-muted md:hidden">{c.label}</span>
                <span>{c.render(row)}</span>
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
