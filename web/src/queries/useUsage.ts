import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

/** One UTC calendar month of stored consumption (T4, D1). */
export interface UsageMonth {
  /** ``YYYY-MM``. */
  month: string;
  tokens_in: number;
  tokens_out: number;
  /** ``null`` whenever ``cost_known`` is false: never a partial sum. */
  cost_usd: number | null;
  cost_known: boolean;
  analyses: number;
  archives: number;
}

export interface Usage {
  /** Newest first; the current month is always present. */
  months: UsageMonth[];
}

/** Read-only monthly consumption from `GET /api/usage`. */
export function useUsage() {
  return useQuery({
    queryKey: ["usage"],
    queryFn: () => api.get<Usage>("/api/usage"),
  });
}
