import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";

export interface User {
  id: number;
  email: string;
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