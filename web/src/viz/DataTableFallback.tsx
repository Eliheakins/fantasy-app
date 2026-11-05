type DataTableFallbackProps = {
  summary?: string;
  /** Accessible name of the table, saying what the chart it stands in for shows. */
  caption?: string;
  columns: readonly string[];
  rows: readonly (readonly (string | number)[])[];
};

/** Text equivalent for a chart: the numbers behind it in a closed <details>. */
export function DataTableFallback({ summary = "Show data", caption, columns, rows }: DataTableFallbackProps) {
  return (
    <details className="text-caption">
      <summary className="flex min-h-[44px] cursor-pointer items-center text-forest">{summary}</summary>
      <table className="mt-1 tabular-nums">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="border-b-[1.5px] border-forest">
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
