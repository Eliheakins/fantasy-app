import { cn } from "@/shared/lib/utils";
import { formatQueryValue } from "@/shared/lib/formatQueryValue";
import type { QueryResult } from "@/shared/types/workbench";

export interface QueryResultTableProps {
  result: QueryResult;
  zebra?: boolean;
  className?: string;
  minWidthClass?: string;
}

export function QueryResultTable({ result, zebra = false, className, minWidthClass = "min-w-[280px]" }: QueryResultTableProps) {
  return (
    <div className={cn("overflow-x-auto rounded-md border border-border", className)}>
      <table className={cn("w-full border-collapse text-left text-sm", minWidthClass)}>
        <thead>
          <tr className="border-b border-border bg-input/50">
            {result.columns.map((col) => (
              <th key={col} className="px-3 py-2 font-medium text-ink-muted">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, i) => (
            <tr key={i} className={cn("border-b border-border/80 last:border-0", zebra && i % 2 === 1 && "bg-input/30")}>
              {result.columns.map((col) => (
                <td key={col} className="px-3 py-2 font-mono text-accent">
                  {formatQueryValue(row[col])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
