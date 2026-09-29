/** Deterministic Spanish number formatting. ICU-free on purpose: the codebase
 * avoids `Intl`/`toLocaleString` so the output is identical across runtimes and
 * matches the narrative convention (dot thousands, comma decimal). */

/**
 * Format a finite number with Spanish separators: dot thousands and comma
 * decimal, at most `maxFractionDigits` fraction digits with trailing zeros
 * stripped. Non-finite values render an em dash; `-0` (and any value rounding
 * to zero) renders `0` without a sign.
 */
export function formatNumberEs(value: number, maxFractionDigits = 6): string {
  if (!Number.isFinite(value)) return "—";
  const fixed = value.toFixed(maxFractionDigits);
  const [rawInt = "0", rawFrac = ""] = fixed.split(".");
  const fraction = rawFrac.replace(/0+$/, "");
  const negative = rawInt.startsWith("-");
  const digits = negative ? rawInt.slice(1) : rawInt;
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  const isZero = /^0*$/.test(digits) && fraction === "";
  const sign = negative && !isZero ? "-" : "";
  return sign + grouped + (fraction ? `,${fraction}` : "");
}

/**
 * Format a table cell for display: `null`/`undefined` become an em dash,
 * numbers use the Spanish formatter, anything else falls back to `String`.
 */
export function formatTableValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return formatNumberEs(value);
  return String(value);
}
