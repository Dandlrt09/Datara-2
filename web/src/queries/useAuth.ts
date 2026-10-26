import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

export interface User {
  id: number;
  email: string;
  /** Scheduled purge deadline in the grace period, or null (S3). */
  pending_deletion_at: string | null;
}

export function useMe() {
  return useQuery({
    queryKey: ["auth", "me"],
    queryFn: () => api.get<User>("/api/auth/me"),
    retry: false,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { email: string; password: string }) =>
      api.post<User>("/api/auth/login", data),
    onSuccess: (user) => {
      qc.setQueryData(["auth", "me"], user);
      qc.invalidateQueries({ queryKey: ["sessions"] });
    },
  });
}

export function useRegister() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { email: string; password: string }) =>
      api.post<User>("/api/auth/register", data),
    onSuccess: (user) => {
      qc.setQueryData(["auth", "me"], user);
    },
  });
}

/**
 * Schedule the account for deletion after the grace period (S2).
 *
 * The server closes every session on success, so the whole cache is dropped —
 * nothing cached is valid after the account is scheduled (S5).
 */
export function useRequestAccountDeletion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { confirmation: string; current_password: string }) =>
      api.post<undefined>("/api/auth/account/delete", data),
    onSuccess: () => {
      qc.clear();
    },
  });
}

/** Cancel a scheduled deletion so the account survives (S3). */
export function useCancelAccountDeletion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<undefined>("/api/auth/account/cancel-deletion"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<undefined>("/api/auth/logout"),
    onSuccess: () => {
      qc.clear();
    },
  });
}

/**
 * Change the signed-in user's password.
 *
 * No cache clearing on success: the server closes the *other* sessions and
 * keeps the current one alive (S4), so the tab that changed the password stays
 * logged in and `GET /api/auth/me` keeps returning the same user.
 */
export function useChangePassword() {
  return useMutation({
    mutationFn: (data: { current_password: string; new_password: string }) =>
      api.post<undefined>("/api/auth/password", data),
  });
}