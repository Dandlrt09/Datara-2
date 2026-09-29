import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
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

/** Page size for files keyset pagination. The backend clamps the `limit`
 * query param to 1..200 and defaults to 50 — this matches it. */
export const FILES_PAGE_SIZE = 50;

/** First page only (D5): no load-more surface, because the app has no
 * per-session files consumer. The endpoint is paginated; this hook requests
 * exactly one page at FILES_PAGE_SIZE. */
export function useFiles(sessionId: string | null) {
  return useQuery({
    queryKey: ["files", sessionId],
    queryFn: () =>
      api.get<UploadedFile[]>(
        `/api/sessions/${sessionId}/files?limit=${FILES_PAGE_SIZE}`,
      ),
    enabled: !!sessionId,
  });
}

/** One raw page: newest-first (`created_at DESC, id DESC`) at most
 * FILES_PAGE_SIZE rows, all with `id < before` when `before` is given. */
async function fetchFilesPage(before?: number): Promise<FileListItem[]> {
  const cursor = before === undefined ? "" : `&before=${before}`;
  return api.get<FileListItem[]>(
    `/api/files?limit=${FILES_PAGE_SIZE}${cursor}`,
  );
}

export interface UseFilesGlobalResult {
  /** Flattened pages, newest-first (page 1 first, older pages appended). */
  data: FileListItem[];
  isLoading: boolean;
  isSuccess: boolean;
  error: Error | null;
  refetch: () => Promise<unknown>;
  /** True while another older page may exist (last page filled the size). */
  hasMore: boolean;
  /** Fetches and appends the next older page; no-op when exhausted. */
  loadMore: () => Promise<void>;
  isLoadingMore: boolean;
}

/** Global files list, accumulated across cursor pages.
 *
 * `useInfiniteQuery` keeps the pages under the `["files","global"]` key, so
 * the upload/delete invalidations (which target `["files"]`) refetch every
 * loaded page coherently — no stale older window survives a delete. The
 * returned `data` stays a flat newest-first `FileListItem[]` so existing
 * consumers (FilesView, the AppShell wizard trigger) are unchanged. */
export function useFilesGlobal(): UseFilesGlobalResult {
  const query = useInfiniteQuery({
    queryKey: ["files", "global"],
    queryFn: ({ pageParam }) => fetchFilesPage(pageParam),
    initialPageParam: undefined as number | undefined,
    // A page that filled the size may have an older sibling: the keyset
    // cursor is that page's oldest id. A short page ends the walk.
    getNextPageParam: (lastPage) =>
      lastPage.length === FILES_PAGE_SIZE
        ? lastPage[lastPage.length - 1]?.id
        : undefined,
  });

  const data = useMemo(
    () => (query.data?.pages ?? []).flat(),
    [query.data],
  );

  return {
    data,
    isLoading: query.isLoading,
    isSuccess: query.isSuccess,
    error: query.error,
    refetch: query.refetch,
    hasMore: query.hasNextPage,
    loadMore: async () => {
      if (query.hasNextPage && !query.isFetchingNextPage) {
        await query.fetchNextPage();
      }
    },
    isLoadingMore: query.isFetchingNextPage,
  };
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

/** Rename a file. Mirrors `useRenameSession` (useSessions.ts). */
export function useRenameFile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ fileId, filename }: { fileId: number; filename: string }) =>
      api.patch<UploadedFile>(`/api/files/${fileId}`, { filename }),
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
