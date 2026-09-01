import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

export interface Message {
  id: number;
  role: string;
  content_text: string;
  code?: string | null;
  artifacts?: unknown[] | null;
  model?: string | null;
  created_at?: string | null;
}

export function useMessages(sessionId: string | null, limit = 50) {
  return useQuery({
    queryKey: ["messages", sessionId],
    queryFn: () =>
      api.get<Message[]>(`/api/sessions/${sessionId}/messages?limit=${limit}`),
    enabled: !!sessionId,
  });
}