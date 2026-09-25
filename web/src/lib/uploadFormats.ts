/**
 * Client single source of truth for accepted upload formats.
 *
 * Mirrors the server allow-list in
 * `server/api/routers/files.py::_SUPPORTED_EXTENSIONS`
 * (`{".csv", ".tsv", ".xlsx", ".json"}`). `.tab` is deliberately excluded:
 * the server rejects it with HTTP 400, so the UI must not offer it.
 *
 * The server and client runtimes are separate (pytest vs vitest), so the
 * mirror is pinned by `web/src/__tests__/uploadFormats.test.ts` plus this
 * comment — not by a cross-language import.
 *
 * Typed as `readonly string[]` (not `as const`) because callers pass a plain
 * `string` to `.includes(ext)`; a literal tuple would reject it.
 */
export const SUPPORTED_UPLOAD_EXTENSIONS: readonly string[] = [
  ".csv",
  ".tsv",
  ".xlsx",
  ".json",
];

/**
 * react-dropzone `accept` map. It corresponds one-to-one with
 * `SUPPORTED_UPLOAD_EXTENSIONS` (enforced by the uploadFormats test) so the
 * two shapes cannot disagree. `.tab` is absent by design.
 */
export const UPLOAD_ACCEPT_MAP: Record<string, string[]> = {
  "text/csv": [".csv"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
  "application/json": [".json"],
  "text/tab-separated-values": [".tsv"],
};

/**
 * Comma-joined extension list for a plain `<input accept>` attribute.
 */
export const UPLOAD_ACCEPT_ATTR: string = SUPPORTED_UPLOAD_EXTENSIONS.join(",");
