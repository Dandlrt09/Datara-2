import { useState } from "react";
import { useUsage } from "../queries/useUsage";
import { formatCost, formatNumber, usePreferences } from "../lib/preferences";
import { colors } from "../design/tokens";

// Same current light inline style as the rest of ProfileView (the Dark Cockpit
// repaint is a later work).
const cardStyle = {
  border: `1px solid ${colors.borderLight}`,
  borderRadius: 8,
  padding: 24,
  marginBottom: 16,
} as const;

const sublabelStyle = {
  color: colors.textMuted,
  fontSize: "0.85em",
  display: "block",
} as const;

/** Spanish month names, index 0 = January. Kept as a plain table (no `Intl`)
 * so the label is deterministic in tests and never depends on the ICU build. */
const MONTH_NAMES = [
  "Enero",
  "Febrero",
  "Marzo",
  "Abril",
  "Mayo",
  "Junio",
  "Julio",
  "Agosto",
  "Septiembre",
  "Octubre",
  "Noviembre",
  "Diciembre",
] as const;

/** Turn the server's `YYYY-MM` into a readable "Octubre 2026".
 *
 * An unparseable value falls back to the raw string, so a malformed month can
 * never render "undefined NaN". */
function formatMonthLabel(month: string): string {
  const [year, rawMonth] = month.split("-");
  const index = Number(rawMonth) - 1;
  if (!Number.isInteger(index) || index < 0 || index >= MONTH_NAMES.length) {
    return month;
  }
  return `${MONTH_NAMES[index]} ${year}`;
}

/**
 * Monthly consumption (T4): stored tokens, cost and analyses per UTC month,
 * one month at a time through a selector.
 *
 * The cost never invents a number: when the server could not price every
 * message of a month (`cost_known` false) the card says "Sin precio conocido"
 * instead of showing a partial sum as if it were the total (S4, D3).
 */
export default function UsageCard() {
  const { data, isLoading } = useUsage();
  const { numberFormat, currencySymbol } = usePreferences();
  const [selected, setSelected] = useState<string | null>(null);

  const months = data?.months ?? [];
  // Fall back to the newest month when nothing is chosen yet, or when a
  // refetch no longer carries the chosen one.
  const chosen = months.some((m) => m.month === selected)
    ? selected
    : (months[0]?.month ?? null);
  const shown = months.find((m) => m.month === chosen) ?? null;

  return (
    <section style={cardStyle} aria-busy={isLoading}>
      <h2 style={{ margin: 0, color: colors.textPrimary }}>Consumo</h2>
      <p style={{ margin: "4px 0 0", ...sublabelStyle }}>
        Tu consumo guardado, mes a mes. Mostramos solo lo que existe: si un mes
        no tiene precio conocido, lo decimos en lugar de estimarlo.
      </p>

      {!isLoading && months.length === 0 && (
        <p style={{ ...sublabelStyle, marginTop: 8 }}>
          Todavía no hay consumo.
        </p>
      )}

      {shown && (
        <>
          <div style={{ marginTop: 16 }}>
            <label htmlFor="usage-month" style={sublabelStyle}>
              Mes
            </label>
            <select
              id="usage-month"
              value={shown.month}
              onChange={(event) => setSelected(event.target.value)}
              style={{
                display: "block",
                marginTop: 4,
                padding: "6px 8px",
                fontSize: 14,
                borderRadius: 6,
                border: `1px solid ${colors.borderLight}`,
                background: "#fff",
                color: colors.textPrimary,
              }}
            >
              {months.map((month) => (
                <option key={month.month} value={month.month}>
                  {formatMonthLabel(month.month)}
                </option>
              ))}
            </select>
          </div>

          <div
            role="group"
            aria-label={shown.month}
            style={{ marginTop: 16 }}
          >
            <h3 style={{ margin: 0, color: colors.textPrimary }}>
              {formatMonthLabel(shown.month)}
            </h3>
            <dl
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
                gap: 12,
                margin: "8px 0 0",
              }}
            >
              {(
                [
                  [
                    "Tokens de entrada",
                    formatNumber(shown.tokens_in, numberFormat),
                  ],
                  [
                    "Tokens de salida",
                    formatNumber(shown.tokens_out, numberFormat),
                  ],
                  [
                    "Análisis ejecutados",
                    formatNumber(shown.analyses, numberFormat),
                  ],
                  [
                    "Análisis guardados",
                    formatNumber(shown.archives, numberFormat),
                  ],
                  [
                    "Costo",
                    shown.cost_known && shown.cost_usd !== null
                      ? formatCost(shown.cost_usd, currencySymbol)
                      : "Sin precio conocido",
                  ],
                ] as [string, string][]
              ).map(([label, value]) => (
                <div key={label}>
                  <dt style={sublabelStyle}>{label}</dt>
                  <dd style={{ margin: 0, color: colors.textPrimary }}>
                    {value}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        </>
      )}
    </section>
  );
}
