import { cn } from "@/lib/utils";
import { formatQueryValue } from "@/stat/lib/formatQueryValue";
import type { QueryResult } from "@/stat/types/workbench";

export interface QueryResultTableProps {
  result: QueryResult;
  className?: string;
  minWidthClass?: string;
}

export function QueryResultTable({
  result,
  className,
  minWidthClass = "min-w-[280px]",
}: QueryResultTableProps) {
  return (
    <div className={cn("overflow-x-auto", className)}>
      <table className={cn("w-full border-collapse text-left text-body", minWidthClass)}>
        <thead>
          <tr className="border-b-[1.5px] border-ink">
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
              className={"border-b border-line last:border-0"}
            >
              {result.columns.map((col) => (
                <td key={col} className="px-3 py-2 tabular-nums text-ink">
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
