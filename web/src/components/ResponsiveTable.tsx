import type { ReactNode } from "react";
import { type Breakpoint, useMinWidth } from "@/hooks/useMediaQuery";
import { cn } from "@/lib/utils";

/** primary: the row's identity (row header, card title). secondary: key numbers, shown on the card.
 * detail: folded under "More" on the card. Unflagged columns are secondary; with no primary flag, column 1 is primary. */
export type ColumnRole = "primary" | "secondary" | "detail";

export type Column<T> = { label: string; render: (row: T) => ReactNode; numeric?: boolean; role?: ColumnRole };

type Props<T> = {
  caption: string;
  columns: readonly Column<T>[];
  rows: readonly T[];
  rowKey: (row: T, index: number) => string;
  /** Emphasised row (my team); the caller also puts a text marker in a cell. */
  isStrong?: (row: T) => boolean;
  /** Width at which the table takes over from cards. lg, because the nav rail leaves ~540 px at 768. */
  breakpoint?: Breakpoint;
};

type FormProps<T> = Omit<Props<T>, "breakpoint">;

function primaryIndex<T>(columns: readonly Column<T>[]): number {
  const flagged = columns.findIndex((c) => c.role === "primary");
  return flagged === -1 ? 0 : flagged;
}

function TableForm<T>({ caption, columns, rows, rowKey, isStrong }: FormProps<T>) {
  const head = primaryIndex(columns);
  return (
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label={caption}>
      <table className="w-full text-body">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-border text-left text-caption text-muted">
            {columns.map((c) => (
              <th key={c.label} scope="col" className={cn("px-2 py-1 font-normal", c.numeric && columns.indexOf(c) !== head && "text-right")}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={rowKey(row, i)} className={cn("border-b border-border", isStrong?.(row) && "border-l-4 border-l-accent font-semibold")}>
              {columns.map((c, ci) => {
                const cls = cn("px-2 py-1 align-top", c.numeric && ci !== head && "text-right tabular-nums");
                return ci === head ? (
                  <th key={c.label} scope="row" className={cn(cls, "text-left [font-weight:inherit] text-text")}>
                    {c.render(row)}
                  </th>
                ) : (
                  <td key={c.label} className={cls}>{c.render(row)}</td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Field<T>({ column, row }: { column: Column<T>; row: T }) {
  return (
    <div className="min-w-0">
      <dt className="text-caption text-muted">{column.label}</dt>
      <dd className={cn(column.numeric && "tabular-nums")}>{column.render(row)}</dd>
    </div>
  );
}

function CardForm<T>({ caption, columns, rows, rowKey, isStrong }: FormProps<T>) {
  const head = columns[primaryIndex(columns)];
  const rest = columns.filter((c) => c !== head);
  const key = rest.filter((c) => c.role !== "detail");
  const more = rest.filter((c) => c.role === "detail");
  return (
    <ul aria-label={caption} className="space-y-2">
      {rows.map((row, i) => (
        <li key={rowKey(row, i)} className={cn("card-flat", isStrong?.(row) && "border-l-4 border-l-accent")}>
          <div className={cn("text-body", isStrong?.(row) ? "font-semibold" : "font-medium")}>{head?.render(row)}</div>
          {key.length > 0 && (
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2">
              {key.map((c) => <Field key={c.label} column={c} row={row} />)}
            </dl>
          )}
          {more.length > 0 && (
            <details className="mt-1">
              <summary className="flex min-h-[44px] cursor-pointer items-center text-caption text-muted">More</summary>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-2 pb-1">
                {more.map((c) => <Field key={c.label} column={c} row={row} />)}
              </dl>
            </details>
          )}
        </li>
      ))}
    </ul>
  );
}

/** A table from the breakpoint up; one card per row below it. */
export function ResponsiveTable<T>({ breakpoint = "lg", ...props }: Props<T>) {
  const wide = useMinWidth(breakpoint);
  return wide ? <TableForm {...props} /> : <CardForm {...props} />;
}
