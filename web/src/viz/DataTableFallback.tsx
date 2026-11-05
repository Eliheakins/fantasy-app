type DataTableFallbackProps = {
  summary?: string;
  columns: readonly string[];
  rows: readonly (readonly (string | number)[])[];
};

/** Text equivalent for a chart: the numbers behind it in a closed <details>. */
export function DataTableFallback({ summary = "Show data", columns, rows }: DataTableFallbackProps) {
  return (
    <details className="text-caption">
      <summary className="flex min-h-[44px] cursor-pointer items-center text-muted">{summary}</summary>
      <table className="mt-1 tabular-nums">
        <thead>
          <tr className="border-b-[1.5px] border-ink">
            {columns.map((c) => (
              <th key={c} scope="col" className="pr-2 text-left font-normal text-muted">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            // Rows are static; labels such as a run time can repeat, so the index is part of the key.
            <tr key={`${i}|${row.join("|")}`} className="border-b border-line">
              {row.map((cell, j) => (
                <td key={columns[j]} className="pr-2">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
