// Experiment scaffolding: which arrangement of the fused provider settings is
// rendered.
//
// The maintainer asked to try the three arrangements in the browser before
// choosing one (see odd/tasks/wizard-settings-fusion.md, S3):
//
//   a — one screen, two modes: guided steps and the full view side by side
//   b — one screen, one view: every field at once, no steps
//   c — two screens: Ajustes (full view) plus /app/setup (guided steps)
//
// The choice arrives as `?variante=a|b|c` and is then remembered *per origin*,
// because the address bar does not survive the app's own navigations: logging in
// sends the user to /app, which redirects without the query string, and the
// choice would silently fall back to the default. With the remembered value, one
// visit per origin is enough — including three servers on three ports, which is
// what the maintainer asked for. A query parameter still wins over the stored
// value, so several tabs can compare arrangements side by side.
//
// This module and the branches it feeds are deleted as soon as one arrangement
// is chosen (T8). Nothing else may depend on it: no rule lives here.

export type SettingsVariant = "a" | "b" | "c";

export const DEFAULT_SETTINGS_VARIANT: SettingsVariant = "a";

export const SETTINGS_VARIANT_LABELS: Record<SettingsVariant, string> = {
  a: "A · una pantalla, dos modos (Guiado / Avanzado)",
  b: "B · una pantalla, una sola vista",
  c: "C · dos pantallas (Ajustes + asistente)",
};

const STORAGE_KEY = "datara.settings-variant";

function isVariant(value: string | null): value is SettingsVariant {
  return value === "a" || value === "b" || value === "c";
}

/** The remembered choice, or null when there is none. Never throws: a browser
 * that denies storage must not break the app for an experiment. */
export function storedSettingsVariant(): SettingsVariant | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return isVariant(raw) ? raw : null;
  } catch {
    return null;
  }
}

function rememberSettingsVariant(variant: SettingsVariant): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, variant);
  } catch {
    // Storage unavailable (private mode, blocked cookies): the parameter keeps
    // working per URL, which is enough for the experiment.
  }
}

/**
 * Resolve the arrangement: the query parameter wins and is remembered; without
 * one, the remembered choice is used; otherwise the default. An unknown value
 * falls back instead of breaking the screen.
 */
export function readSettingsVariant(raw: string | null): SettingsVariant {
  if (isVariant(raw)) {
    rememberSettingsVariant(raw);
    return raw;
  }
  return storedSettingsVariant() ?? DEFAULT_SETTINGS_VARIANT;
}
