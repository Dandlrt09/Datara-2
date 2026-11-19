import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

/** Shortest lock password the backend accepts (F1 / T4, D4), mirrored so the
 * forms stop the user before the request leaks a 422. */
export const LOCAL_PASSWORD_MIN_LENGTH = 8;

export interface User {
  id: number;
  /** The account address, or null for a local profile, which has none (F1/T5). */
  email: string | null;
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

/**
 * The machine's identity state before any session (F1 / T2b / T2c / T3).
 *
 * Unauthenticated on purpose: the first-run screen needs it before it holds a
 * session, to choose between showing the creation form, opening the existing
 * profile silently (L10), or keeping the email login. `hosted_accounts` is
 * true when the database already holds email accounts: the local profile is
 * only OFFERED on an empty database (D3), so an existing install is sent to
 * `/login` instead of the creation form.
 */
export interface LocalProfileStatus {
  exists: boolean;
  hosted_accounts: boolean;
  /** The optional lock (T4/D4) is on: the profile has a password and must not
   * be opened silently. */
  locked: boolean;
}

export function useLocalProfileStatus() {
  return useQuery({
    queryKey: ["auth", "local-profile"],
    queryFn: () => api.get<LocalProfileStatus>("/api/auth/local-profile"),
    retry: false,
  });
}

/**
 * The one-time payload the lock and rescue routes answer (T4/D4).
 *
 * The raw key is shown exactly once and never stored in the app: only the
 * backend keeps its hash, and the key itself cannot be read back.
 */
export interface LocalRescueKey {
  rescue_key: string;
}

/**
 * Protect the local profile with a password (F1 / T4, D4).
 *
 * Requires a session — turning the lock on is an act on a profile the caller is
 * already inside. On success it answers the rescue key ONCE; that key is the
 * only way back if the password is forgotten, so the caller must show it and
 * keep it nowhere in the app.
 */
export function useLocalProfileLock() {
  return useMutation({
    mutationFn: (data: { password: string }) =>
      api.post<LocalRescueKey>("/api/auth/local-profile/lock", data),
  });
}

/**
 * Open a locked local profile with its password (F1 / T4, D4).
 *
 * The way back in once the 8h session expired, so it is unauthenticated. The
 * server answers the user and mints the session cookie, so the payload is
 * cached exactly like login does.
 */
export function useLocalProfileOpen() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { password: string }) =>
      api.post<User>("/api/auth/local-profile/open", data),
    onSuccess: (user) => {
      qc.setQueryData(["auth", "me"], user);
      qc.invalidateQueries({ queryKey: ["sessions"] });
    },
  });
}

/**
 * Recover a locked local profile with its one-time rescue key (F1 / T4, D4).
 *
 * Unauthenticated like open. On success the key is ROTATED, so the response
 * carries the NEW raw key and the caller must show it once. The server opens a
 * session but returns only the key, not the user: the `me` cache is refetched
 * so the app can see the new session when it lands.
 */
export function useLocalProfileRescue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { rescue_key: string; new_password: string }) =>
      api.post<LocalRescueKey>("/api/auth/local-profile/rescue", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });
}

/**
 * Create the local profile, or open it when it already exists (F1 / T2b / T2c).
 *
 * Get-or-create (L10): with a name the server creates the profile (201); with
 * no name it opens the existing one (200) and ignores the body. Either way it
 * starts the session, so the user payload is written into the `me` cache the
 * same way login does.
 */
export function useLocalProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { name?: string }) =>
      api.post<User>("/api/auth/local-profile", data),
    onSuccess: (user) => {
      qc.setQueryData(["auth", "me"], user);
      qc.invalidateQueries({ queryKey: ["sessions"] });
    },
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
 * Create the account and send the verification email.
 *
 * `name` is optional (register-experience S2): the signup form lets it empty and
 * omits the key, and the server then falls back to the email-derived name.
 * `terms_version` is required (terms-of-use D5): it is the version the person
 * read, and the server records it as the text that was accepted.
 *
 * Register no longer authenticates (D4): there is no session cookie and no
 * `me` payload to cache, so the mutation has no cache side effects. The person
 * goes to `/check-email` and only gets a session after verifying the address.
 */
export function useRegister() {
  return useMutation({
    mutationFn: (data: {
      email: string;
      password: string;
      name?: string;
      terms_version: string;
    }) => api.post<User>("/api/auth/register", data),
  });
}

/**
 * Redeem the emailed verification token (S3/D10).
 *
 * The screen POSTs the token; verifying does not open a session, it only
 * confirms the address and sends the person to login.
 */
export function useVerifyEmail() {
  return useMutation({
    mutationFn: (data: { token: string }) =>
      api.post<undefined>("/api/auth/verify-email", data),
  });
}

/**
 * Ask for a fresh verification link (S3/D6).
 *
 * Always answers 202, whether the address exists or not, so the UI shows the
 * same confirmation either way and cannot be used to enumerate accounts.
 */
export function useResendVerification() {
  return useMutation({
    mutationFn: (data: { email: string }) =>
      api.post<undefined>("/api/auth/resend-verification", data),
  });
}

/** Start password recovery (S4/D6); the server always answers 202. */
export function useForgotPassword() {
  return useMutation({
    mutationFn: (data: { email: string }) =>
      api.post<undefined>("/api/auth/forgot-password", data),
  });
}

/** Set a new password from the emailed reset token (S4). */
export function useResetPassword() {
  return useMutation({
    mutationFn: (data: { token: string; new_password: string }) =>
      api.post<undefined>("/api/auth/reset-password", data),
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