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

/** Emitted by the backend no-dataset guard: the model produced code for a
 * session with no attached files, so the sandbox was never invoked. */
export const NO_DATASET_CODE = "session/no_dataset";

/** Emitted by the backend guard when the session HAS attached files but
 * none could be profiled (lazy re-profile failed), so the turn could not
 * run. Distinct from NO_DATASET_CODE so the UI does not claim there are no
 * files when there are. */
export const FILE_NOT_PROFILED_CODE = "session/file_not_profiled";

/** Reserved taxonomy code — registered everywhere, emitted nowhere by design.
 *
 * It is deliberately registered here (recognized by ``isKnownErrorCode`` and
 * given a presentation below) so a future emitter can ship it without a
 * frontend release, but NO runtime path emits it today: model adequacy is
 * decided at configuration time via the bench (see the RESERVED note in
 * ``server/services/error_taxonomy.py``). Do not delete it as dead code. */
export const MODEL_INADEQUATE_CODE = "model/inadequate";

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

/** Informational, actionable banner: the fix is to attach a dataset and
 * re-run the turn (the retry action re-sends the same question). */
const NO_DATASET: ErrorPresentation = {
  variant: "info",
  title: "Esta sesión no tiene datos",
  action: RETRY,
  actionLabel: RETRY_LABEL,
};

/** Warning, actionable banner: files are attached but could not be
 * profiled, so the turn could not run. Re-upload or delete and retry. */
const FILE_NOT_PROFILED: ErrorPresentation = {
  variant: "warning",
  title: "Archivos sin procesar",
  action: RETRY,
  actionLabel: RETRY_LABEL,
};

/** Reserved (registered, no emitter yet): the selected model cannot handle
 * the task; the fix is to choose a capable model in Settings. */
const MODEL_INADEQUATE: ErrorPresentation = {
  variant: "warning",
  title: "Modelo no adecuado para esta tarea",
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
    code === MODEL_INADEQUATE_CODE ||
    code === NO_DATASET_CODE ||
    code === FILE_NOT_PROFILED_CODE ||
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
  if (code === NO_DATASET_CODE) {
    return NO_DATASET;
  }
  if (code === FILE_NOT_PROFILED_CODE) {
    return FILE_NOT_PROFILED;
  }
  if (code === "model/not_allowed") {
    return { variant: "warning", title: "Modelo no disponible", action: "none" };
  }
  if (code === MODEL_INADEQUATE_CODE) {
    return MODEL_INADEQUATE;
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
  // internal/error (Enmienda 1) and any unknown or missing code share the
  // generic danger fallback. (model/inadequate is registered above.)
  return {
    variant: "error",
    title: "Error",
    action: RETRY,
    actionLabel: RETRY_LABEL,
  };
}
