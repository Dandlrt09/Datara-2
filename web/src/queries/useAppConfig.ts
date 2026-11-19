import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

/** `local` is the packaged desktop app (no email); `hosted` is the multi-user
 * deployment with the email flows. */
export type AppMode = "local" | "hosted";

export interface AppConfig {
  mode: AppMode;
}

/** The deployment mode. Read before login (the endpoint is unauthenticated),
 * because it decides which screens exist. */
export function useAppConfig() {
  return useQuery({
    queryKey: ["app-config"],
    queryFn: () => api.get<AppConfig>("/api/app-config"),
    // The mode is fixed for the lifetime of the process.
    staleTime: Infinity,
  });
}

/** Whether the email-based screens (register, verification, recovery) apply.
 * Fails open: if the mode cannot be read, behave as before this existed. */
export function emailFlowsEnabled(
  config: { data?: AppConfig; isError?: boolean } | undefined,
): boolean {
  if (!config) return true;
  return config.isError === true || config.data?.mode === "hosted";
}
