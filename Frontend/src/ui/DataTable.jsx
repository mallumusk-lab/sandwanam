import { Fragment } from "react";

/**
 * Semantic table. On narrow screens rows become labelled cards (stack = true),
 * so no information is lost to horizontal scrolling.
 *
 * columns: [{ key, header, render?(row), numeric?, className? }]
 * detail(row): optional; when it returns content, a full-width row follows the row
 * (joined to it in the stacked layout).
 */
export function DataTable({ columns, rows, rowKey, caption, stack = true, empty, detail, footer, className = "" }) {
  if (!rows.length && empty) return empty;
  return (
    <div className="table-wrap">
      <table className={`table${stack ? " table-stack" : ""}${className ? ` ${className}` : ""}`}>
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
          {rows.map((row, index) => {
            const extra = detail ? detail(row) : null;
            return (
              <Fragment key={rowKey ? rowKey(row) : index}>
                <tr className={extra ? "has-detail" : undefined}>
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      data-label={typeof column.header === "string" ? column.header : column.headerText ?? (typeof column.header?.props?.children === "string" ? column.header.props.children : undefined)}
                      className={[column.numeric ? "num" : "", column.className ?? ""].filter(Boolean).join(" ") || undefined}
                    >
                      {column.render ? column.render(row, index) : row[column.key] ?? "—"}
                    </td>
                  ))}
                </tr>
                {extra ? (
                  <tr className="table-detail">
                    <td colSpan={columns.length}>{extra}</td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
        {footer ? <tfoot>{footer}</tfoot> : null}
      </table>
    </div>
  );
}
