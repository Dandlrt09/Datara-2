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

/** Client-side cap for the probe call. Larger than the server's 5s httpx
 * timeout so the server usually answers first; this only catches a hung
 * transport (proxy/DNS/server never responding) that would otherwise leave
 * the caller in its "checking" state forever. */
export const MODEL_FETCH_TIMEOUT_MS = 15000;

export function useFetchModels() {
  const mutation = useMutation({
    mutationFn: async (): Promise<ModelsResponse> => {
      const controller = new AbortController();
      let timedOut = false;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const timeout = new Promise<ModelsResponse>((resolve) => {
        timer = setTimeout(() => {
          timedOut = true;
          controller.abort();
          resolve({
            models: [],
            error: { code: "timeout", message: "Request timed out" },
          });
        }, MODEL_FETCH_TIMEOUT_MS);
      });
      try {
        // Race instead of relying solely on the fetch abort: a hung
        // transport (proxy/DNS) may never surface the AbortError, and the
        // same shape the server returns still reaches the caller.
        return await Promise.race([
          api.post<ModelsResponse>("/api/settings/models", undefined, {
            signal: controller.signal,
          }),
          timeout,
        ]);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") {
          return {
            models: [],
            error: { code: "timeout", message: "Request timed out" },
          };
        }
        throw err;
      } finally {
        if (timer !== undefined) clearTimeout(timer);
        if (timedOut) controller.abort();
      }
    },
  });

  return {
    models: mutation.data?.models || [],
    isLoading: mutation.isPending,
    error: mutation.error || (mutation.data?.error ? new Error(mutation.data.error.message) : null),
    fetchModels: mutation.mutateAsync,
  };
}