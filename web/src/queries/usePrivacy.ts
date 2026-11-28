import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { PrivacyLevel } from "../lib/privacy";

/** Mirrors server `FilePrivacyEntry` (server/api/routers/privacy.py). */
export interface FilePrivacyEntry {
  file_id: number;
  filename: string;
  /** The file's own override; `null` means "inherit the session". */
  privacy_level: string | null;
  /** The level that actually applies once the session default is resolved. */
  effective_level: string;
  column_aliases: Record<string, string> | null;
}

/** Mirrors server `SessionPrivacyResponse`. */
export interface SessionPrivacy {
  session_id: string;
  privacy_level: string;
  levels: string[];
  files: FilePrivacyEntry[];
}

/** One outgoing dataset in the preview payload. */
export interface OutgoingProfile {
  file_id: number;
  filename: string;
  format: string;
  /** Neutral staged name (the real storage path never leaves the server). */
  path: string;
  row_count: number | null;
  /** Ordinal position of the selected sheet; the label never leaves the server. */
  sheet_index: number | null;
  profile: {
    columns: { name: string; dtype: string }[];
    stats: Record<string, unknown>;
    sample: unknown[];
  };
}

/** A file with no profile, reported so the viewer can name it. */
export interface UnprofiledFile {
  file_id: number;
  filename: string;
  format: string;
}

/** Mirrors the preview endpoint: the exact payload the chat path ships. */
export interface PrivacyPreview {
  profiles: OutgoingProfile[];
  unprofiled_files: UnprofiledFile[];
}

/** Session privacy key. The `["privacy"]` prefix is the invalidation target. */
export function sessionPrivacyKey(sessionId: string | null) {
  return ["privacy", sessionId] as const;
}

/** Session level plus each file's own and effective level. */
export function useSessionPrivacy(sessionId: string | null) {
  return useQuery({
    queryKey: sessionPrivacyKey(sessionId),
    queryFn: () =>
      api.get<SessionPrivacy>(`/api/sessions/${sessionId}/privacy`),
    enabled: !!sessionId,
  });
}

/** Set the session default. Refreshes the session privacy (and its preview). */
export function useUpdateSessionPrivacy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      sessionId,
      privacyLevel,
    }: {
      sessionId: string;
      privacyLevel: PrivacyLevel;
    }) =>
      api.put<SessionPrivacy>(`/api/sessions/${sessionId}/privacy`, {
        privacy_level: privacyLevel,
      }),
    onSuccess: (data) =>
      qc.invalidateQueries({ queryKey: ["privacy", data.session_id] }),
  });
}

/** Set one file's override and/or aliases. */
export function useUpdateFilePrivacy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      fileId,
      privacyLevel,
      columnAliases,
    }: {
      fileId: number;
      /** `null` clears the override; omitted leaves it untouched. */
      privacyLevel?: PrivacyLevel | null;
      columnAliases?: Record<string, string> | null;
    }) =>
      api.patch<FilePrivacyEntry>(`/api/files/${fileId}/privacy`, {
        ...(privacyLevel !== undefined
          ? { privacy_level: privacyLevel }
          : {}),
        ...(columnAliases !== undefined
          ? { column_aliases: columnAliases }
          : {}),
      }),
    // A file change can shift any session that lists it, and the response
    // carries no session id, so the whole privacy tree is refreshed.
    onSuccess: () => qc.invalidateQueries({ queryKey: ["privacy"] }),
  });
}

/** The exact outgoing payload. `enabled` keeps it lazy until the viewer opens. */
export function usePrivacyPreview(
  sessionId: string | null,
  enabled = true,
) {
  return useQuery({
    queryKey: ["privacy", sessionId, "preview"],
    queryFn: () =>
      api.get<PrivacyPreview>(`/api/sessions/${sessionId}/privacy/preview`),
    enabled: !!sessionId && enabled,
  });
}
