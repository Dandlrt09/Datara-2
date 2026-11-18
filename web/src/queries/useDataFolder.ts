import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

/** Where the analyst's data lives. The location is an at-boot decision, so it
 * is read before login and is not a settings row. */
export interface DataFolderStatus {
  /** False while the analyst has not chosen a location yet (first run). */
  decided: boolean;
  /** The folder the server would use right now. */
  path: string;
  /** The recommended folder (the OS default directory). */
  default_path: string;
}

/** The result of deciding: the status plus the cloud client syncing the
 * chosen folder, when there is one (S6). */
export interface DataFolderDecision extends DataFolderStatus {
  synced_client: string | null;
}

/** Read the current data folder and whether the choice is still open. */
export function useDataFolder() {
  return useQuery({
    queryKey: ["data-folder"],
    queryFn: () => api.get<DataFolderStatus>("/api/data-folder"),
  });
}

/** Decide the data folder. Only valid while it is still undecided; the server
 * answers 409 `already_decided` afterwards. */
export function useChooseDataFolder() {
  return useMutation({
    mutationFn: (path: string) =>
      api.put<DataFolderDecision>("/api/data-folder", { path }),
  });
}
