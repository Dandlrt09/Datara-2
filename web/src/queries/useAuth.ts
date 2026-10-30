import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

export interface User {
  id: number;
  email: string;
  /** The name the user chose in Perfil, or null to fall back to the email (T1). */
  name: string | null;
  /** Scheduled purge deadline in the grace period, or null (S3). */
  pending_deletion_at: string | null;
}

/** One open auth session as returned by `GET /api/auth/sessions` (T2.4). */
export interface ActiveSession {
  id: number;
  user_agent: string | null;
  created_at: string;
  last_seen_at: string;
  is_current: boolean;
}

/** The sessions payload: the list plus the unseen-new-session marker. */
export interface ActiveSessions {
  sessions: ActiveSession[];
  new_session_at: string | null;
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

/**
 * Create the account and sign in.
 *
 * `name` is optional (register-experience S2): the signup form lets it empty and
 * omits the key, and the server then falls back to the email-derived name.
 * `terms_version` is required (terms-of-use D5): it is the version the person
 * read, and the server records it as the text that was accepted.
 *
 * The chat-session list is invalidated exactly like `useLogin` does (D5): a
 * brand-new account starts with an empty list, but a browser that still holds a
 * previous account's cache would otherwise list sessions that are not its own.
 */
export function useRegister() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      email: string;
      password: string;
      name?: string;
      terms_version: string;
    }) => api.post<User>("/api/auth/register", data),
    onSuccess: (user) => {
      qc.setQueryData(["auth", "me"], user);
      qc.invalidateQueries({ queryKey: ["sessions"] });
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

/**
 * Save the display name the user picked in Perfil (T1).
 *
 * The response is the updated user, so it is written straight into the `me`
 * cache instead of invalidating it: the profile and the sidebar re-render with
 * the new name on the same tick. An empty name is a valid value — the server
 * stores NULL and the display goes back to the email-derived name (D3).
 */
export function useUpdateName() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name: string }) =>
      api.patch<User>("/api/auth/me", data),
    onSuccess: (user) => {
      qc.setQueryData(["auth", "me"], user);
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

/**
 * List the signed-in user's open auth sessions, most recent activity first.
 *
 * Uses the `["auth", "sessions"]` cache key on purpose: `["sessions"]` already
 * belongs to the *chat* sessions (`useSessions.ts`) and the two must not share
 * a cache entry.
 */
export function useActiveSessions() {
  return useQuery({
    queryKey: ["auth", "sessions"],
    queryFn: () => api.get<ActiveSessions>("/api/auth/sessions"),
  });
}

/** Close one session by id. The server rejects the caller's own session. */
export function useCloseSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.delete<undefined>(`/api/auth/sessions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["auth", "sessions"] }),
  });
}

/** Close every session except the caller's ("close the others"). */
export function useCloseOtherSessions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete<undefined>("/api/auth/sessions"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["auth", "sessions"] }),
  });
}

/** Mark the new-session notice as seen so it stops showing. */
export function useAcknowledgeNewSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<undefined>("/api/auth/sessions/notice-ack"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["auth", "sessions"] }),
  });
}