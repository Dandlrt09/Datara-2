import type { CSSProperties } from "react";
import type { ProfileSummary } from "../queries/useFiles";

/** Defensive view of one column's stats: any field may be absent. */
interface ColumnStats {
  null_count?: unknown;
  unique_count?: unknown;
  min?: unknown;
  max?: unknown;
}

/**
 * Render one stat cell deterministically.
 *
 * D4: `null`/`undefined`/non-finite → em dash; finite numbers → grouped with up
 * to 6 fraction digits; anything else → `String(v)`. Kept module-local so the
 * formatting rule is unit-testable and shared by every cell.
 */
export function formatStat(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "—";
    return Number(value).toLocaleString("en-US", { maximumFractionDigits: 6 });
  }
  return String(value);
}

export interface ProfileTableProps {
  /** The serialized profile: `schema.columns` drives the rows, `stats` by name. */
  profile: ProfileSummary;
}

const cellStyle: CSSProperties = {
  padding: "4px 8px",
  borderBottom: "1px solid #eee",
  textAlign: "left",
  verticalAlign: "top",
};

const headerStyle: CSSProperties = {
  ...cellStyle,
  borderBottom: "2px solid #ccc",
};

/**
 * Presentational per-column profile table plus a nested "Raw JSON" collapsible.
 *
 * Rows come from `schema.columns`; each column's stats are looked up by name, so
 * a column missing from `stats` still renders (with em-dash cells) and a null or
 * partial `stats` never throws (D3). The full JSON stays reachable nested below
 * (D5), byte-identical to the previous raw dump.
 */
export function ProfileTable({ profile }: ProfileTableProps) {
  const columns = profile?.schema?.columns ?? [];
  const stats = (profile?.stats ?? {}) as Record<string, ColumnStats | undefined>;

  return (
    <div style={{ minWidth: 280 }}>
      <div style={{ maxHeight: 200, overflow: "auto" }}>
        <table style={{ borderCollapse: "collapse", width: "100%", fontSize: "0.85em" }}>
          <thead>
            <tr>
              <th style={headerStyle}>Columna</th>
              <th style={headerStyle}>Tipo</th>
              <th style={headerStyle}>Nulos</th>
              <th style={headerStyle}>Únicos</th>
              <th style={headerStyle}>Mín</th>
              <th style={headerStyle}>Máx</th>
            </tr>
          </thead>
          <tbody>
            {columns.map((column, index) => {
              const columnStats = stats[column.name];
              return (
                <tr key={`${column.name}-${index}`}>
                  <td style={cellStyle}>{column.name}</td>
                  <td style={cellStyle}>{column.dtype}</td>
                  <td style={cellStyle}>{formatStat(columnStats?.null_count)}</td>
                  <td style={cellStyle}>{formatStat(columnStats?.unique_count)}</td>
                  <td style={cellStyle}>{formatStat(columnStats?.min)}</td>
                  <td style={cellStyle}>{formatStat(columnStats?.max)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <details>
        <summary>Raw JSON</summary>
        <pre style={{ fontSize: "0.85em", maxHeight: 200, overflow: "auto" }}>
          {JSON.stringify(profile, null, 2)}
        </pre>
      </details>
    </div>
  );
}
