import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

export interface UploadedFile {
  id: number;
  filename: string;
  format: string;
  row_count?: number;
  size_bytes: number;
  created_at: string;
}

export interface FileListItem extends UploadedFile {
  chat_session_id: string;
  session_title: string | null;
}

interface ProfileSummary {
  schema: { columns: string[] };
  stats: Record<string, unknown>;
  sample: unknown[];
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
    }: {
      sessionId: string;
      file: File;
    }) => {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`/api/sessions/${sessionId}/files`, {
        method: "POST",
        credentials: "include",
        body: form,
      });
      if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
      return res.json() as Promise<UploadedFile & { profile_summary: ProfileSummary }>;
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