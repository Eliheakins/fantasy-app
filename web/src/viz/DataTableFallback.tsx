type DataTableFallbackProps = {
  summary?: string;
  columns: readonly string[];
  rows: readonly (readonly (string | number)[])[];
};

/** Text equivalent for a chart: the numbers behind it in a closed <details>. */
export function DataTableFallback({ summary = "Show data", columns, rows }: DataTableFallbackProps) {
  return (
    <details className="text-caption">
      <summary className="cursor-pointer text-muted">{summary}</summary>
      <table className="mt-1 tabular-nums">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c} scope="col" className="pr-2 text-left font-normal text-muted">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.join("|")}>
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
