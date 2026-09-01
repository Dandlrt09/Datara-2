import { useMemo, useState } from "react";

interface DataFrameTableProps {
  columns: string[];
  rows: unknown[][];
}

export default function DataFrameTable({ columns, rows }: DataFrameTableProps) {
  const [sortKey, setSortKey] = useState<number | null>(null);
  const [sortAsc, setSortAsc] = useState(true);

  const sortedRows = useMemo(() => {
    if (sortKey === null) return rows;
    return [...rows].sort((a, b) => {
      const va = a[sortKey];
      const vb = b[sortKey];
      if (va == null) return 1;
      if (vb == null) return -1;
      const cmp = typeof va === "number" ? va - (vb as number) : String(va).localeCompare(String(vb));
      return sortAsc ? cmp : -cmp;
    });
  }, [rows, sortKey, sortAsc]);

  function handleSort(colIdx: number) {
    if (sortKey === colIdx) {
      setSortAsc((prev) => !prev);
    } else {
      setSortKey(colIdx);
      setSortAsc(true);
    }
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            {columns.map((col, i) => (
              <th
                key={i}
                onClick={() => handleSort(i)}
                style={{
                  cursor: "pointer",
                  borderBottom: "2px solid #ccc",
                  padding: "8px 12px",
                  textAlign: "left",
                  userSelect: "none",
                }}
              >
                {col}
                {sortKey === i ? (sortAsc ? " ▲" : " ▼") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((row, ri) => (
            <tr key={ri}>
              {row.map((cell, ci) => (
                <td
                  key={ci}
                  style={{
                    padding: "6px 12px",
                    borderBottom: "1px solid #eee",
                  }}
                >
                  {cell == null ? "—" : String(cell)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}