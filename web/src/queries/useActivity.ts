import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

/** One entry of the mixed activity feed (T6). */
export interface ActivityEvent {
  kind: "chat" | "file" | "archive";
  title: string;
  at: string;
}

/** Current-month (UTC) totals, computed live by the server (T6). */
export interface MonthSummary {
  chats: number;
  analyses: number;
  files: number;
  rows: number;
  archives: number;
}

export interface Activity {
  events: ActivityEvent[];
  month: MonthSummary;
}

/** Read-only personal activity log from `GET /api/activity`. */
export function useActivity() {
  return useQuery({
    queryKey: ["activity"],
    queryFn: () => api.get<Activity>("/api/activity"),
  });
}
