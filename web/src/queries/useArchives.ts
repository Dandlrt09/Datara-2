import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

export interface Archive {
  id: number;
  name: string;
  chat_session: string;
  created_at: string;
}

export interface ArchiveDetail extends Archive {
  payload?: Record<string, unknown>;
}

export function useArchives() {
  return useQuery({
    queryKey: ["archives"],
    queryFn: () => api.get<Archive[]>("/api/archives"),
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