import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

export interface UserSettings {
  user_id: number;
  /** True when an API key is stored server-side. The key itself never
   * leaves the server. */
  has_api_key: boolean;
  default_model?: string | null;
}

export function useSettings() {
  return useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<UserSettings>("/api/settings"),
  });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { api_key?: string; default_model?: string }) =>
      api.put<UserSettings>("/api/settings", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["settings"] }),
  });
}