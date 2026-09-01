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