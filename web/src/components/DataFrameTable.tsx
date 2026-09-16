import { useMemo, useState } from "react";

interface DataFrameTableProps {
  columns: string[];
  rows: unknown[][];
}

/** Escape a single CSV field: quote and double-quote fields that contain
 * commas, quotes or newlines (RFC 4180 subset). Null/undefined → empty. */
function escapeCsvField(value: unknown): string {
  if (value == null) return "";
  const s = String(value);
  if (/[",\n\r]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

/**
 * Build the CSV text for a table artifact. Pure function, exported for tests.
 * Prepend a UTF-8 BOM so Excel renders Spanish accents correctly; rows are
 * LF-joined (fine for modern tools). Exports exactly the captured head-20
 * rows that are visible — full-dataset export is a separate future task.
 */
export function buildCsv(columns: string[], rows: unknown[][]): string {
  const header = columns.map(escapeCsvField).join(",");
  const body = rows.map((row) =>
    columns.map((_, i) => escapeCsvField(row[i])).join(","),
  );
  return "\uFEFF" + [header, ...body].join("\n") + "\n";
}

/** Trigger a client-side download for a data URL. Extracted so tests can
 * stub the anchor click without touching the DOM. */
function downloadDataUrl(dataUrl: string, filename: string) {
  const a = document.createElement("a");
  a.href = dataUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
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

  /** Export the currently visible (sorted) rows as CSV. */
  function handleDownloadCsv() {
    const csv = buildCsv(columns, sortedRows);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    downloadDataUrl(url, "datara-tabla.csv");
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          marginBottom: 4,
        }}
      >
        <button
          onClick={handleDownloadCsv}
          style={{
            background: "#fff",
            color: "#555",
            border: "1px solid #ccc",
            borderRadius: 4,
            cursor: "pointer",
            fontSize: "0.75em",
            padding: "2px 8px",
          }}
          title="Descarga las filas visibles como archivo CSV"
        >
          Descargar CSV
        </button>
      </div>
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
    </div>
  );
}