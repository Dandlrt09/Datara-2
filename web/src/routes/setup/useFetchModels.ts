import { useMutation } from "@tanstack/react-query";
import { api } from "../../lib/api";

export interface ModelInfo {
  id: string;
  name: string;
}

export interface FetchModelsError {
  code: "no_provider" | "provider_error" | "timeout" | "network";
  message: string;
}

export interface ModelsResponse {
  models: ModelInfo[];
  error: FetchModelsError | null;
}

export function useFetchModels() {
  const mutation = useMutation({
    mutationFn: async (): Promise<ModelsResponse> => {
      const response = await api.post<ModelsResponse>("/api/settings/models");
      return response;
    },
  });

  return {
    models: mutation.data?.models || [],
    isLoading: mutation.isPending,
    error: mutation.error || (mutation.data?.error ? new Error(mutation.data.error.message) : null),
    fetchModels: mutation.mutateAsync,
  };
}