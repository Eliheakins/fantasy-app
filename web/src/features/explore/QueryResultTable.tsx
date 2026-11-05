import { cn } from "@/lib/utils";
import { formatQueryValue } from "@/stat/lib/formatQueryValue";
import type { QueryResult } from "@/stat/types/workbench";

export interface QueryResultTableProps {
  result: QueryResult;
  zebra?: boolean;
  className?: string;
  minWidthClass?: string;
}

export function QueryResultTable({
  result,
  zebra = false,
  className,
  minWidthClass = "min-w-[280px]",
}: QueryResultTableProps) {
  return (
    <div className={cn("overflow-x-auto rounded-md border border-border", className)}>
      <table className={cn("w-full border-collapse text-left text-body", minWidthClass)}>
        <thead>
          <tr className="border-b border-border bg-surface">
            {result.columns.map((col) => (
              <th key={col} className="px-3 py-2 font-medium text-muted">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {result.rows.map((row, i) => (
            <tr
              key={i}
              className={cn("border-b border-border/80 last:border-0", zebra && i % 2 === 1 && "bg-surface")}
            >
              {result.columns.map((col) => (
                <td key={col} className="px-3 py-2 tabular-nums text-text">
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
