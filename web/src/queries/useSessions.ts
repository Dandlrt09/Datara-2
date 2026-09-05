import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useSseStore } from "../stores/useSseStore";

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  is_streaming?: boolean;
}

export function useSessions() {
  const sseConnected = useSseStore((s) => s.sseConnected);
  return useQuery({
    queryKey: ["sessions"],
    queryFn: () => api.get<ChatSession[]>("/api/sessions"),
    refetchInterval: sseConnected ? false : 10_000,
    // Heal a dead/failed sessions query the moment the user focuses the tab
    // (global default is false; without this a failed initial fetch leaves an
    // empty sidebar until the next invalidation).
    refetchOnWindowFocus: true,
  });
}

export function useCreateSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (title?: string) =>
      api.post<ChatSession>("/api/sessions", { title }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
}

export function useDeleteSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete(`/api/sessions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["sessions"] }),
  });
}