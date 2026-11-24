/** Declared privacy levels (F6).
 *
 * Mirrors `PRIVACY_LEVELS` in `server/services/privacy.py`: the closed set of
 * levels a session or a file can carry. `full` is the default and keeps the
 * payload unchanged; the other three progressively hide detail. Product copy
 * stays in neutral Spanish with tuteo (project convention).
 */

export type PrivacyLevel = "full" | "aggregates" | "schema" | "masked";

/** Closed set, in the server's order. */
export const PRIVACY_LEVELS: PrivacyLevel[] = [
  "full",
  "aggregates",
  "schema",
  "masked",
];

/** The four level labels, exactly as the roadmap names them. */
export const PRIVACY_LEVEL_LABELS: Record<PrivacyLevel, string> = {
  full: "Completo",
  aggregates: "Agregados",
  schema: "Solo esquema",
  masked: "Enmascarado",
};

/** One-line description of what each level sends to the model provider. */
export const PRIVACY_LEVEL_DESCRIPTIONS: Record<PrivacyLevel, string> = {
  full: "Se envía todo el perfil: nombres de columna, estadísticas y valores de muestra.",
  aggregates: "Se envían los agregados por columna, sin valores ni filas de muestra.",
  schema: "Solo se envían los nombres y tipos de columna, sin estadísticas ni muestras.",
  masked:
    "Los valores y las filas se envían enmascarados, sin medias ni extremos.",
};

/** Sentinel used by the select controls for "no override". */
export const INHERIT_LEVEL = "inherit";

/** Label for the inherit option (files only; the session always has a level). */
export const INHERIT_LEVEL_LABEL = "Heredar de la sesión";
