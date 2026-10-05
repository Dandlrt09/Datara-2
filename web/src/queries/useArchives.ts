import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { api } from "../lib/api";

export interface Archive {
  id: number;
  name: string;
  /** Nullable: the chat session may have been deleted (ON DELETE SET NULL). */
  chat_session: string | null;
  /** Optional in the API schema (`str | None`); the DB column is NOT NULL. */
  created_at: string | null;
  /** File names captured in the snapshot, in snapshot order. */
  files: string[];
  /** Rows in the last table artifact (or the file fallback); null if unknown. */
  row_count: number | null;
  /** Columns in the last table artifact; null if no table artifact exists. */
  column_count: number | null;
}

/** The list-card shape returned by `GET /api/archives` and `PATCH /api/archives/{id}`. */
export type ArchiveListItem = Archive;

export interface ArchiveDetail
  extends Omit<Archive, "files" | "row_count" | "column_count"> {
  /** Null when the stored `payload_json` is malformed (server never 500s). */
  payload?: Record<string, unknown> | null;
}

/** Page size for the archives keyset. The backend clamps `limit` to 1..200 and
 * defaults to 50 — this matches it. The list response is a bare array; the
 * client infers `hasMore` from `len === limit`. */
export const ARCHIVES_PAGE_SIZE = 50;

export type ArchivesOrder = "newest" | "oldest";

export interface UseArchivesParams {
  /** Case- and accent-insensitive name substring; empty means no filter. */
  q?: string;
  order?: ArchivesOrder;
}

/** Archives list, accumulated across keyset pages. Consumers flatten
 * `data.pages`; `hasNextPage` / `fetchNextPage` drive «Cargar más».
 *
 * Search and order are resolved server-side: they are part of the query key,
 * so changing either starts a fresh first page. The cursor is `before` for
 * newest-first and `after` for oldest-first. */
export function useArchives({
  q = "",
  order = "newest",
}: UseArchivesParams = {}) {
  return useInfiniteQuery({
    queryKey: ["archives", "list", q, order],
    queryFn: ({ pageParam }) => {
      let url = `/api/archives?limit=${ARCHIVES_PAGE_SIZE}&order=${order}`;
      if (q) url += `&q=${encodeURIComponent(q)}`;
      if (pageParam != null) {
        const cursor = order === "newest" ? "before" : "after";
        url += `&${cursor}=${pageParam}`;
      }
      return api.get<Archive[]>(url);
    },
    initialPageParam: null as number | null,
    getNextPageParam: (lastPage) =>
      lastPage.length === ARCHIVES_PAGE_SIZE
        ? lastPage[lastPage.length - 1].id
        : undefined,
  });
}

export function useCreateArchive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { chat_session: string; name: string }) =>
      api.post<ArchiveDetail>("/api/archives", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["archives"] }),
  });
}

export function useArchiveDetail(id: number | null) {
  return useQuery({
    queryKey: ["archives", id],
    queryFn: () => api.get<ArchiveDetail>(`/api/archives/${id}`),
    enabled: !!id,
  });
}

export function useDeleteArchive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.delete<void>(`/api/archives/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["archives"] }),
  });
}

export function useRenameArchive() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) =>
      api.patch<ArchiveListItem>(`/api/archives/${id}`, { name }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["archives"] }),
  });
}
