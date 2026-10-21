/**
 * Semantic table. On narrow screens rows become labelled cards (stack = true),
 * so no information is lost to horizontal scrolling.
 *
 * columns: [{ key, header, render?(row), numeric?, className? }]
 */
export function DataTable({ columns, rows, rowKey, caption, stack = true, empty }) {
  if (!rows.length && empty) return empty;
  return (
    <div className="table-wrap">
      <table className={`table${stack ? " table-stack" : ""}`}>
        {caption ? <caption>{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col"
                className={[column.numeric ? "num" : "", column.className ?? ""].filter(Boolean).join(" ") || undefined}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={rowKey ? rowKey(row) : index}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  data-label={typeof column.header === "string" ? column.header : undefined}
                  className={[column.numeric ? "num" : "", column.className ?? ""].filter(Boolean).join(" ") || undefined}
                >
                  {column.render ? column.render(row) : row[column.key] ?? "—"}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
