import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

/** Mirrors server `FileResponse` (server/api/routers/files.py). */
export interface UploadedFile {
  id: number;
  filename: string;
  format: string;
  size_bytes: number;
  row_count?: number | null;
  created_at?: string | null;
  has_profile?: boolean;
}

/** Mirrors server `FileListItem` (server/api/routers/files.py). */
export interface FileListItem extends UploadedFile {
  chat_session_id: string;
  session_title: string | null;
}

/** Mirrors server `FileCreateResponse` (server/api/routers/files.py). */
export interface FileCreateResult {
  id: number;
  filename: string;
  format: string;
  size_bytes: number;
  row_count?: number | null;
  encoding?: string | null;
  sheet_name?: string | null;
  sheets?: string[] | null;
  created_at?: string | null;
}

export interface ProfileSchemaColumn {
  name: string;
  dtype: string;
}

/** Mirrors server `ProfileResponse` (server/api/routers/files.py). */
export interface ProfileSummary {
  file_id: number;
  schema: { columns: ProfileSchemaColumn[] };
  stats: Record<string, unknown>;
  sample: unknown[];
  generated_at?: string | null;
}

/** Upload failure that keeps the HTTP status available to callers. */
export class UploadError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = "UploadError";
    this.status = status;
  }
}

export function useFiles(sessionId: string | null) {
  return useQuery({
    queryKey: ["files", sessionId],
    queryFn: () =>
      api.get<UploadedFile[]>(`/api/sessions/${sessionId}/files`),
    enabled: !!sessionId,
  });
}

export function useFilesGlobal() {
  return useQuery({
    queryKey: ["files", "global"],
    queryFn: () => api.get<FileListItem[]>("/api/files"),
  });
}

export function useUploadFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      sessionId,
      file,
      signal,
    }: {
      sessionId: string;
      file: File;
      signal?: AbortSignal;
    }) => {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`/api/sessions/${sessionId}/files`, {
        method: "POST",
        credentials: "include",
        body: form,
        signal,
      });
      if (!res.ok) {
        // The server sends ``{"detail": ...}`` for domain errors (409
        // duplicate name, 400 parse failure). Surface that detail so callers
        // can map it; a non-JSON body must never throw here, so parsing is
        // best-effort and falls back to the status message.
        let detail: string | undefined;
        try {
          const body = (await res.json()) as { detail?: unknown };
          if (typeof body?.detail === "string" && body.detail.trim()) {
            detail = body.detail;
          }
        } catch {
          // Non-JSON error body — fall back to the status message.
        }
        throw new UploadError(res.status, detail || `Upload failed: ${res.status}`);
      }
      return res.json() as Promise<FileCreateResult>;
    },
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["files"] }),
  });
}

export function useDeleteFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (fileId: number) => api.delete(`/api/files/${fileId}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["files"] }),
  });
}

export function useProfile(fileId: number | null) {
  return useQuery({
    queryKey: ["profile", fileId],
    queryFn: () => api.get<ProfileSummary>(`/api/files/${fileId}/profile`),
    enabled: !!fileId,
  });
}

export interface FileSheets {
  sheets: string[];
  default_sheet: string;
}

/** Lazy sheet list for a file; disabled until the caller opts in so the
 * picker only fetches when the user opens it. */
export function useFileSheets(fileId: number | null, enabled = true) {
  return useQuery({
    queryKey: ["file-sheets", fileId],
    queryFn: () => api.get<FileSheets>(`/api/files/${fileId}/sheets`),
    enabled: enabled && !!fileId,
  });
}

export interface SheetSelectResult {
  file_id: number;
  filename: string;
  sheet_name: string;
  sheets: string[];
  row_count: number | null;
}

/** Re-profile an XLSX file against another sheet in place. */
export function useSelectFileSheet() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      fileId,
      sheetName,
    }: {
      fileId: number;
      sheetName: string;
    }) =>
      api.post<SheetSelectResult>(`/api/files/${fileId}/sheet`, {
        sheet_name: sheetName,
      }),
    onSuccess: (_data, variables) => {
      qc.invalidateQueries({ queryKey: ["files"] });
      qc.invalidateQueries({ queryKey: ["profile", variables.fileId] });
      // The per-row picker reads default_sheet from this query; without the
      // invalidation it would keep offering the pre-switch sheet.
      qc.invalidateQueries({ queryKey: ["file-sheets", variables.fileId] });
    },
  });
}
