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
    queryFn: async () => {
      // The API returns messages newest-first (created_at DESC, id DESC —
      // the keyset-pagination contract); the chat renders oldest→newest,
      // so honor the documented "client reverses" contract here. Without
      // this reversal the assistant answer rendered ABOVE the user's
      // question after every refetch.
      const msgs = await api.get<Message[]>(
        `/api/sessions/${sessionId}/messages?limit=${limit}`,
      );
      return [...msgs].reverse();
    },
    enabled: !!sessionId,
  });
}