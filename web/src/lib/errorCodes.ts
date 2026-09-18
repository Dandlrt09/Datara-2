/** Presentation mapping from typed taxonomy codes to ErrorCard props.
 *
 * Pure module — no React, no side effects — so the mapping is exhaustively
 * unit-testable and ChatView stays a mechanical consumer. Normative source:
 * the error-rendering spec table + Enmienda 1 (internal/error).
 */

/** Visual family; matches ErrorCard's ErrorCardVariant. */
export type ErrorVariant = "error" | "warning" | "info";

/** What the banner's action button does. */
export type ErrorAction = "retry-turn" | "go-settings" | "none";

export interface ErrorPresentation {
  variant: ErrorVariant;
  /** Professional Spanish title (spec-pinned per code family). */
  title: string;
  action: ErrorAction;
  /** Button copy; omitted when there is no button (action "none"). */
  actionLabel?: string;
}

const RETRY: "retry-turn" = "retry-turn";
const RETRY_LABEL = "Reintentar";

const GO_SETTINGS: ErrorPresentation = {
  variant: "error",
  title: "Error de autenticación",
  action: "go-settings",
  actionLabel: "Ir a Ajustes",
};

/** The verbatim `${type}: ${message}` degradation (today's banner format)
 * applies whenever the code is missing or outside the taxonomy. */
export function isKnownErrorCode(code: string | null | undefined): boolean {
  if (!code) return false;
  return (
    code === "internal/error" ||
    code === "model/not_allowed" ||
    code.startsWith("auth/") ||
    code.startsWith("sandbox/") ||
    code.startsWith("llm/")
  );
}

/** Resolve the banner presentation for a taxonomy code. Unknown or missing
 * codes degrade to the generic danger fallback (renderable, never crashes). */
export function resolveErrorPresentation(
  code: string | null | undefined,
): ErrorPresentation {
  if (code === "auth/invalid_key" || code === "auth/no_credits") {
    return GO_SETTINGS;
  }
  if (code === "model/not_allowed") {
    return { variant: "warning", title: "Modelo no disponible", action: "none" };
  }
  if (code?.startsWith("sandbox/")) {
    return {
      variant: "error",
      title: "Error de ejecución",
      action: RETRY,
      actionLabel: RETRY_LABEL,
    };
  }
  if (code?.startsWith("llm/")) {
    return {
      variant: "error",
      title: "Error del modelo",
      action: RETRY,
      actionLabel: RETRY_LABEL,
    };
  }
  // internal/error (Enmienda 1), reserved model/inadequate, and any unknown
  // or missing code share the generic danger fallback.
  return {
    variant: "error",
    title: "Error",
    action: RETRY,
    actionLabel: RETRY_LABEL,
  };
}
