/** Relative-time formatting in neutral Spanish.
 *
 * Uses the platform's `Intl.RelativeTimeFormat("es", { numeric: "always" })`
 * with explicit unit thresholds, so the phrasing is always the numeric form the
 * design mandates (e.g. "hace 2 días", "hace 1 semana"). Anything under a
 * minute reads "hace un momento" so a just-created análisis never shows
 * "hace 0 segundos". An unparseable ISO string falls back to
 * `toLocaleDateString()`.
 */

const MINUTE_MS = 60_000;
const HOUR_MS = 60 * MINUTE_MS;
const DAY_MS = 24 * HOUR_MS;
const WEEK_MS = 7 * DAY_MS;
const MONTH_MS = 30 * DAY_MS;
const YEAR_MS = 365 * DAY_MS;

const relativeFormat = new Intl.RelativeTimeFormat("es", { numeric: "always" });

export function formatRelativeTimeEs(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return date.toLocaleDateString();
  }

  const diffMs = date.getTime() - Date.now();
  const absMs = Math.abs(diffMs);

  if (absMs < MINUTE_MS) {
    return "hace un momento";
  }
  if (absMs < HOUR_MS) {
    return relativeFormat.format(Math.round(diffMs / MINUTE_MS), "minute");
  }
  if (absMs < DAY_MS) {
    return relativeFormat.format(Math.round(diffMs / HOUR_MS), "hour");
  }
  if (absMs < WEEK_MS) {
    return relativeFormat.format(Math.round(diffMs / DAY_MS), "day");
  }
  if (absMs < MONTH_MS) {
    return relativeFormat.format(Math.round(diffMs / WEEK_MS), "week");
  }
  if (absMs < YEAR_MS) {
    return relativeFormat.format(Math.round(diffMs / MONTH_MS), "month");
  }
  return relativeFormat.format(Math.round(diffMs / YEAR_MS), "year");
}
