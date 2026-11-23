/* F5 (S5): the session's crossing — the recipe that joins two of its files.
 *
 * The wire shapes mirror `server/api/routers/crossings.py`; the types live
 * here (no other surface consumes them) instead of a shared contract module.
 *
 * The panel owns its two reads (the session's files and a file's profile)
 * because the chat screen composes it over `useFiles`, whose module is
 * partially mocked by the chat tests. The profile read deliberately uses the
 * same `["profile", fileId]` key as `useProfile` (useFiles.ts), so both
 * surfaces share one cache entry and one request.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import type { ProfileSummary, UploadedFile } from "./useFiles";

/** The join kinds `pd.merge` understands by name (server `JoinKind`). */
export type JoinKind = "inner" | "left" | "right" | "outer";

/** The stored crossing recipe (`store.get_crossing`), filenames included. */
export interface Crossing {
  id: number;
  chat_session: string;
  left_file_id: number;
  right_file_id: number;
  left_key: string;
  right_key: string;
  how: JoinKind;
  created_at?: string | null;
  left_filename: string;
  right_filename: string;
}

/** The imbalance the server counts with pandas when a crossing is confirmed
 * (S6/A2). Present ONLY in the confirmation response — never in a later GET. */
export interface CrossingDiagnostics {
  left_rows: number;
  right_rows: number;
  matched_rows: number;
  left_only_rows: number;
  right_only_rows: number;
  result_rows: number;
}

/** `POST /sessions/{id}/crossings` answer: the recipe plus its imbalance. */
export interface ConfirmedCrossing extends Crossing {
  diagnostics: CrossingDiagnostics;
}

/** The model's proposal (S3): keys, join kind and its why (English prose). */
export interface CrossingProposal {
  left_key: string;
  right_key: string;
  how: JoinKind;
  reason: string;
}

/** Machine-readable outcome of a proposal, so the UI writes its own copy. */
export type CrossingProposalCode =
  | "proposal_not_found"
  | "proposal_unavailable"
  | null;

/** `POST /sessions/{id}/crossings/propose` answer. */
export interface CrossingProposalResponse {
  proposal: CrossingProposal | null;
  code: CrossingProposalCode;
  reason?: string;
}

/** The recipe the analyst confirms. */
export interface CrossingInput {
  left_file_id: number;
  right_file_id: number;
  left_key: string;
  right_key: string;
  how: JoinKind;
}

/** Page size of the crossing file pickers. The endpoint
 * `GET /api/sessions/{id}/files` declares
 * `limit: int = Query(50, ge=1, le=200)` (server/api/routers/files.py), so
 * 200 is that endpoint's hard upper bound. The pickers show ONE page on
 * purpose — no pagination in this slice — so a session with more files than
 * this offers only the first page instead of silently loading more. */
export const CROSSING_FILES_PAGE_SIZE = 200;

/** The session's files, for the two file pickers.
 *
 * The key lives UNDER the `["files"]` prefix on purpose: every file mutation
 * (upload/delete/rename/sheet switch in useFiles.ts) invalidates that prefix,
 * and React Query invalidates by key prefix. A distinct key under the family
 * still lets the panel keep its own one-page shape (`CROSSING_FILES_PAGE_SIZE`).
 * Without this, a freshly uploaded file would not appear in the pickers until
 * the panel remounts. */
export function useCrossingFiles(sessionId: string | null) {
  return useQuery({
    queryKey: ["files", "crossing", sessionId],
    queryFn: () =>
      api.get<UploadedFile[]>(
        `/api/sessions/${sessionId}/files?limit=${CROSSING_FILES_PAGE_SIZE}`,
      ),
    enabled: !!sessionId,
  });
}

/** One file's profile, for the column options of its picker. Shares the
 * `["profile", fileId]` cache entry with `useProfile`. */
export function useCrossingProfile(fileId: number | null) {
  return useQuery({
    queryKey: ["profile", fileId],
    queryFn: () => api.get<ProfileSummary>(`/api/files/${fileId}/profile`),
    enabled: !!fileId,
  });
}

/** The session's active crossing, or `null` when there is none. */
export function useCrossing(sessionId: string | null) {
  return useQuery({
    queryKey: ["crossing", sessionId],
    queryFn: () =>
      api.get<{ crossing: Crossing | null }>(
        `/api/sessions/${sessionId}/crossings`,
      ),
    enabled: !!sessionId,
  });
}

/** Ask the model for a crossing of two files. Stores nothing. */
export function useProposeCrossing(sessionId: string | null) {
  return useMutation({
    mutationFn: (input: { left_file_id: number; right_file_id: number }) =>
      api.post<CrossingProposalResponse>(
        `/api/sessions/${sessionId}/crossings/propose`,
        input,
      ),
  });
}

/** Confirm (and store) the crossing, replacing any previous one. */
export function useConfirmCrossing(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: CrossingInput) =>
      api.post<ConfirmedCrossing>(`/api/sessions/${sessionId}/crossings`, input),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["crossing", sessionId] }),
  });
}

/** Remove the session's active crossing. Idempotent server-side. */
export function useDeleteCrossing(sessionId: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete(`/api/sessions/${sessionId}/crossings`),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["crossing", sessionId] }),
  });
}
