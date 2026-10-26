/** Display preferences: the single client-side source of truth for how the
 * user wants numbers, dates, the USD cost label and the "open" behavior
 * rendered.
 *
 * The backend (`server/services/preferences.py`) resolves every preference to
 * an effective value and `GET /api/settings` always answers with one, so the
 * client never has to guess. `DEFAULT_PREFERENCES` mirrors the server defaults
 * and is also the React context default, which keeps a component rendered
 * without a provider (a unit test, or a surface outside the app shell) working
 * exactly as before preferences existed.
 *
 * The formatters are pure and ICU-free on purpose, matching the existing
 * `formatNumbers.ts` / `relativeTime.ts` convention: identical output across
 * runtimes. The Spanish branches delegate to those existing helpers so their
 * output — and the tests that pin it — cannot drift.
 */

import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useSettings, type UserSettings } from "../queries/useSettings";
import { formatNumberEs } from "./formatNumbers";
import { formatRelativeTimeEs, toUtcIso } from "./relativeTime";

export type NumberFormat = "es" | "intl";
export type DateFormat = "relative" | "absolute";
export type CurrencySymbol = "US$" | "$" | "USD" | "none";
export type OpenBehavior = "new_session" | "last_session";

/** The four effective preferences, in client casing. */
export interface Preferences {
  numberFormat: NumberFormat;
  dateFormat: DateFormat;
  currencySymbol: CurrencySymbol;
  openBehavior: OpenBehavior;
}

/** Mirror of `server/services/preferences.py::DEFAULTS`. Every value is the
 * behavior that predated preferences, so adopting them changes nothing. */
export const DEFAULT_PREFERENCES: Preferences = {
  numberFormat: "es",
  dateFormat: "relative",
  currencySymbol: "US$",
  openBehavior: "new_session",
};

const CURRENCY_SYMBOLS: readonly CurrencySymbol[] = ["US$", "$", "USD", "none"];

/** Resolve a settings payload to effective preferences, defensively defaulting
 * any missing or unknown value (the server already normalizes; this is the
 * client's own safety net for mocked/partial payloads). */
export function effectivePreferences(
  settings: Partial<UserSettings> | null | undefined,
): Preferences {
  const currency = settings?.currency_symbol;
  return {
    numberFormat: settings?.number_format === "intl" ? "intl" : "es",
    dateFormat: settings?.date_format === "absolute" ? "absolute" : "relative",
    currencySymbol:
      currency && CURRENCY_SYMBOLS.includes(currency as CurrencySymbol)
        ? (currency as CurrencySymbol)
        : "US$",
    openBehavior:
      settings?.open_behavior === "last_session" ? "last_session" : "new_session",
  };
}

/** Format a finite number in the chosen convention: dot thousands / comma
 * decimal for Spanish, comma thousands / dot decimal for international.
 * At most `maxFractionDigits` fraction digits, trailing zeros stripped;
 * non-finite renders an em dash and any value rounding to zero loses its sign. */
export function formatNumber(
  value: number,
  numberFormat: NumberFormat = "es",
  maxFractionDigits = 6,
): string {
  if (numberFormat === "es") return formatNumberEs(value, maxFractionDigits);
  if (!Number.isFinite(value)) return "—";

  const fixed = value.toFixed(maxFractionDigits);
  const [rawInt = "0", rawFrac = ""] = fixed.split(".");
  const fraction = rawFrac.replace(/0+$/, "");
  const negative = rawInt.startsWith("-");
  const digits = negative ? rawInt.slice(1) : rawInt;
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const isZero = /^0*$/.test(digits) && fraction === "";
  const sign = negative && !isZero ? "-" : "";
  return sign + grouped + (fraction ? `.${fraction}` : "");
}

/** Format a table cell for display: `null`/`undefined` become an em dash,
 * numbers use the chosen number format, anything else falls back to `String`. */
export function formatTableValue(
  value: unknown,
  numberFormat: NumberFormat = "es",
): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return formatNumber(value, numberFormat);
  return String(value);
}

/** Format an app timestamp: the relative phrasing (existing
 * `formatRelativeTimeEs`) or a fixed `dd/mm/aaaa`. An absolute date that
 * cannot be parsed renders an em dash rather than "Invalid Date". */
export function formatTimestamp(
  iso: string,
  dateFormat: DateFormat = "relative",
): string {
  if (dateFormat === "relative") return formatRelativeTimeEs(iso);
  const date = new Date(toUtcIso(iso));
  if (Number.isNaN(date.getTime())) return "—";
  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  return `${day}/${month}/${date.getFullYear()}`;
}

/** Format a Datara USD cost. D1: the preference only picks the label, the
 * amount is never converted; `"none"` renders the bare number. The amount
 * keeps today's Spanish decimal comma with four decimals. */
export function formatCost(
  usd: number,
  currencySymbol: CurrencySymbol = "US$",
): string {
  const amount = usd.toFixed(4).replace(".", ",");
  return currencySymbol === "none" ? amount : `${currencySymbol} ${amount}`;
}

const PreferencesContext = createContext<Preferences>(DEFAULT_PREFERENCES);

/** Provide the effective preferences to every descendant. Reads the shared
 * `["settings"]` query, so mounting it does not add a request. While the query
 * is loading (or errored) the defaults are served, matching the pre-preference
 * rendering. */
export function PreferencesProvider({ children }: { children: ReactNode }) {
  // `useSettings` resolves to the shared query result; guard its shape so a
  // stubbed hook (or a future loading-only result) cannot take down the shell.
  const settings = useSettings();
  const data = settings?.data;
  const value = useMemo(() => effectivePreferences(data), [data]);
  return (
    <PreferencesContext.Provider value={value}>
      {children}
    </PreferencesContext.Provider>
  );
}

/** The effective preferences. Outside a provider this is
 * `DEFAULT_PREFERENCES`, so a component rendered in isolation still works. */
export function usePreferences(): Preferences {
  return useContext(PreferencesContext);
}
